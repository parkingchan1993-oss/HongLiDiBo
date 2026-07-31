#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在统一回测内核上运行MA250可信基线与参数邻域验证。"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from backtest_core import BacktestConfig, Bar, Signal, run_backtest, run_buy_and_hold


BASE = Path(__file__).resolve().parent
DEFAULT_DATA = BASE / "history_klines.json"
DEFAULT_OUTPUT = BASE / "outputs" / "ma250_baseline_results.json"


@dataclass(frozen=True)
class MA250Parameters:
    lookback: int = 250
    deep_buy_threshold: float = -3.0
    reduce_threshold: float = 3.0
    exit_threshold: float = 7.0
    deep_buy_uptrend_weight: float = 1.0
    deep_buy_downtrend_weight: float = 0.75
    neutral_weight: float = 0.50
    reduce_weight: float = 0.25
    exit_weight: float = 0.0


def load_bars(path: Path) -> list[Bar]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Bar(
        date=str(item["date"]),
        open=float(item["open"]),
        high=float(item["high"]),
        low=float(item["low"]),
        close=float(item["close"]),
        volume=float(item.get("volume", 0.0)),
    ) for item in raw]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rolling_mean(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            result[i] = running / period
    return result


def build_signals(bars: list[Bar], params: MA250Parameters) -> tuple[dict[str, Signal], list[dict]]:
    closes = [bar.close for bar in bars]
    ma = rolling_mean(closes, params.lookback)
    signals: dict[str, Signal] = {}
    records: list[dict] = []
    for i in range(params.lookback - 1, len(bars)):
        if ma[i] is None:
            continue
        deviation = (closes[i] / ma[i] - 1.0) * 100.0
        slope = None
        if i > params.lookback - 1 and ma[i - 1] is not None:
            slope = (ma[i] / ma[i - 1] - 1.0) * 100.0

        if deviation <= params.deep_buy_threshold:
            if slope is not None and slope > 0:
                weight = params.deep_buy_uptrend_weight
                regime = "深度负偏离且MA上行"
            else:
                weight = params.deep_buy_downtrend_weight
                regime = "深度负偏离且MA未上行"
        elif deviation >= params.exit_threshold:
            weight = params.exit_weight
            regime = "高正偏离退出"
        elif deviation >= params.reduce_threshold:
            weight = params.reduce_weight
            regime = "正偏离减仓"
        else:
            weight = params.neutral_weight
            regime = "中性区"

        values = {
            "close": round(closes[i], 8),
            "ma250": round(ma[i], 8),
            "deviation_pct": round(deviation, 8),
            "ma250_slope_pct": round(slope, 8) if slope is not None else None,
        }
        signals[bars[i].date] = Signal(
            date=bars[i].date,
            target_weight=weight,
            reason=regime,
            values=values,
        )
        records.append({"date": bars[i].date, "target_weight": weight, "regime": regime, **values})
    return signals, records


def summarize_signal_events(records: list[dict], threshold: float) -> dict:
    daily = [row for row in records if row["deviation_pct"] <= threshold]
    events = []
    previous_inside = False
    for row in records:
        inside = row["deviation_pct"] <= threshold
        if inside and not previous_inside:
            events.append(row["date"])
        previous_inside = inside
    return {"daily_observations": len(daily), "entry_events": len(events), "entry_dates": events}


def evaluate(
    bars: list[Bar],
    params: MA250Parameters,
    cost_bps: float,
    annual_cash_rate: float,
    annual_risk_free_rate: float,
    rebalance_band: float,
) -> tuple[dict, dict, list[dict]]:
    signals, records = build_signals(bars, params)
    config = BacktestConfig(
        initial_cash=100.0,
        transaction_cost_bps=cost_bps,
        annual_cash_rate=annual_cash_rate,
        annual_risk_free_rate=annual_risk_free_rate,
        rebalance_band=rebalance_band,
    )
    strategy = run_backtest(bars, signals, config)
    first_signal_date = records[0]["date"]
    benchmark = run_buy_and_hold(bars, first_signal_date, config)
    return {
        "parameters": asdict(params),
        "config": strategy.config,
        "metrics": strategy.metrics,
        "benchmark_metrics": benchmark.metrics,
        "excess_total_return_pct": round(
            strategy.metrics["total_return_pct"] - benchmark.metrics["total_return_pct"], 4
        ),
        "strategy_ledger": strategy.ledger,
        "trades": strategy.trades,
        "benchmark_ledger": benchmark.ledger,
        "benchmark_trades": benchmark.trades,
    }, summarize_signal_events(records, params.deep_buy_threshold), records


def parameter_neighborhood(bars: list[Bar], cost_bps: float, cash_rate: float, risk_free_rate: float) -> list[dict]:
    rows = []
    for buy in (-2.0, -3.0, -4.0):
        for reduce in (2.0, 3.0, 4.0):
            for exit_threshold in (6.0, 7.0, 8.0):
                params = MA250Parameters(
                    deep_buy_threshold=buy,
                    reduce_threshold=reduce,
                    exit_threshold=exit_threshold,
                )
                result, _, _ = evaluate(bars, params, cost_bps, cash_rate, risk_free_rate, 0.0)
                metrics = result["metrics"]
                rows.append({
                    "deep_buy_threshold": buy,
                    "reduce_threshold": reduce,
                    "exit_threshold": exit_threshold,
                    "total_return_pct": metrics["total_return_pct"],
                    "max_drawdown_pct": metrics["max_drawdown_pct"],
                    "sharpe": metrics["sharpe"],
                    "trade_count": metrics["trade_count"],
                    "cumulative_turnover": metrics["cumulative_turnover"],
                    "excess_total_return_pct": result["excess_total_return_pct"],
                })
    return sorted(rows, key=lambda row: (row["sharpe"], row["total_return_pct"]), reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cash-rate", type=float, default=0.0, help="年化现金收益率，如0.015")
    parser.add_argument("--risk-free-rate", type=float, default=0.0, help="Sharpe年化无风险利率")
    args = parser.parse_args()

    bars = load_bars(args.data)
    base_params = MA250Parameters()
    transaction_cost_bps = 1.0
    result, signal_summary, signal_records = evaluate(
        bars, base_params, transaction_cost_bps,
        args.cash_rate, args.risk_free_rate, 0.0
    )

    output = {
        "meta": {
            "strategy": "MA250偏离+趋势方向可信基线",
            "data_file": str(args.data.resolve()),
            "data_sha256": file_sha256(args.data),
            "bars": len(bars),
            "date_start": bars[0].date,
            "date_end": bars[-1].date,
            "execution_rule": "T日收盘生成信号，T+1交易日开盘执行",
            "cost_rule": "按单边成交名义金额计提",
            "return_type": "价格收益，不含指数分红再投资",
        },
        "base_parameters": asdict(base_params),
        "signal_summary": signal_summary,
        "current_signal": signal_records[-1],
        "transaction_cost_bps": transaction_cost_bps,
        "cost_1bp": result,
        "parameter_neighborhood_cost_1bp": parameter_neighborhood(
            bars, transaction_cost_bps, args.cash_rate, args.risk_free_rate
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已保存: {args.output}")
    metrics = result["metrics"]
    print(
        "cost_1bp",
        f"收益={metrics['total_return_pct']:+.2f}%",
        f"回撤={metrics['max_drawdown_pct']:.2f}%",
        f"Sharpe={metrics['sharpe']:.3f}",
        f"交易={metrics['trade_count']}",
        f"超额={result['excess_total_return_pct']:+.2f}%",
    )


if __name__ == "__main__":
    main()
