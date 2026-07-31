#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""点时正确的单资产日频仓位回测内核。

约束：
1. 信号只能使用 T 日及以前数据。
2. T 日收盘信号最早在 T+1 日开盘执行。
3. 成本按单边成交名义金额计提。
4. 输出逐日账本与逐笔交易日志，保证结果可复算。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Signal:
    date: str
    target_weight: float
    reason: str
    values: Mapping[str, float | None]


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100.0
    transaction_cost_bps: float = 0.0
    annual_cash_rate: float = 0.0
    annual_risk_free_rate: float = 0.0
    rebalance_band: float = 0.0
    rebalance_on_target_change_only: bool = True
    trading_days_per_year: int = 252


@dataclass
class BacktestResult:
    config: dict
    metrics: dict
    ledger: list[dict]
    trades: list[dict]


def validate_bars(bars: Sequence[Bar]) -> None:
    if len(bars) < 2:
        raise ValueError("至少需要2根K线")
    previous = ""
    for index, bar in enumerate(bars):
        if previous and bar.date <= previous:
            raise ValueError(f"日期必须严格递增: index={index}, date={bar.date}")
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            raise ValueError(f"价格必须为正数: {bar.date}")
        if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
            raise ValueError(f"OHLC关系非法: {bar.date}")
        previous = bar.date


def _metrics(values: Sequence[float], trading_days: int, annual_rf: float) -> dict:
    if len(values) < 2 or values[0] <= 0:
        raise ValueError("净值序列不足或初值非法")
    returns = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))]
    years = (len(values) - 1) / trading_days
    total_return = values[-1] / values[0] - 1.0
    annual_return = (values[-1] / values[0]) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1.0)
    daily_rf = (1.0 + annual_rf) ** (1.0 / trading_days) - 1.0
    excess = [ret - daily_rf for ret in returns]
    volatility = pstdev(returns) * sqrt(trading_days) if len(returns) > 1 else 0.0
    sharpe = mean(excess) / pstdev(returns) * sqrt(trading_days) if len(returns) > 1 and pstdev(returns) > 0 else 0.0
    calmar = annual_return / abs(max_drawdown) if max_drawdown < 0 else 0.0
    return {
        "total_return_pct": round(total_return * 100, 4),
        "annual_return_pct": round(annual_return * 100, 4),
        "annual_volatility_pct": round(volatility * 100, 4),
        "max_drawdown_pct": round(max_drawdown * 100, 4),
        "sharpe": round(sharpe, 4),
        "calmar": round(calmar, 4),
        "observations": len(values),
    }


def run_backtest(
    bars: Sequence[Bar],
    signals: Mapping[str, Signal],
    config: BacktestConfig = BacktestConfig(),
) -> BacktestResult:
    """运行T日信号、T+1开盘执行的回测。

    ``signals`` 的键是信号形成日。只有前一交易日的信号会在当前开盘使用。
    净值序列从第一个可执行信号日的前一日收盘开始，初始状态为全现金。
    """
    validate_bars(bars)
    if config.initial_cash <= 0:
        raise ValueError("初始资金必须为正数")
    if config.transaction_cost_bps < 0 or config.rebalance_band < 0:
        raise ValueError("成本与调仓带不能为负数")
    if not signals:
        raise ValueError("没有可用信号")

    date_to_index = {bar.date: i for i, bar in enumerate(bars)}
    signal_indices = sorted(date_to_index[date] for date in signals if date in date_to_index)
    if not signal_indices:
        raise ValueError("信号日期与K线日期没有交集")
    first_signal_index = signal_indices[0]
    if first_signal_index + 1 >= len(bars):
        raise ValueError("首个信号之后没有可执行交易日")

    start_index = first_signal_index
    cash = float(config.initial_cash)
    shares = 0.0
    total_cost = 0.0
    cumulative_turnover = 0.0
    ledger: list[dict] = []
    trades: list[dict] = []

    ledger.append({
        "date": bars[start_index].date,
        "signal_date": None,
        "execution_price": None,
        "target_weight": 0.0,
        "actual_weight": 0.0,
        "turnover": 0.0,
        "transaction_cost": 0.0,
        "cash": round(cash, 10),
        "shares": 0.0,
        "close": bars[start_index].close,
        "equity": round(cash, 10),
        "daily_return": 0.0,
    })

    daily_cash_rate = (1.0 + config.annual_cash_rate) ** (1.0 / config.trading_days_per_year) - 1.0
    cost_rate = config.transaction_cost_bps / 10000.0

    for i in range(start_index + 1, len(bars)):
        bar = bars[i]
        previous_bar = bars[i - 1]
        previous_equity = ledger[-1]["equity"]
        cash *= 1.0 + daily_cash_rate
        signal = signals.get(previous_bar.date)
        transaction_cost = 0.0
        turnover = 0.0
        execution_price = None
        target_weight = ledger[-1]["target_weight"]

        if signal is not None:
            previous_target = target_weight
            target_weight = min(1.0, max(0.0, float(signal.target_weight)))
            equity_at_open = cash + shares * bar.open
            current_weight = shares * bar.open / equity_at_open if equity_at_open > 0 else 0.0
            target_changed = abs(target_weight - previous_target) > 1e-12
            should_rebalance = (
                target_changed if config.rebalance_on_target_change_only
                else abs(target_weight - current_weight) > config.rebalance_band
            )
            if should_rebalance and abs(target_weight - current_weight) > config.rebalance_band:
                target_notional = equity_at_open * target_weight
                current_notional = shares * bar.open
                trade_notional = target_notional - current_notional
                transaction_cost = abs(trade_notional) * cost_rate
                new_cash = cash - trade_notional - transaction_cost
                if new_cash < -1e-9:
                    # 成本会使满仓买入略微超出现金，按可用现金缩减买单。
                    if trade_notional <= 0:
                        raise RuntimeError("卖出后现金不应为负")
                    affordable_trade = cash / (1.0 + cost_rate)
                    trade_notional = min(trade_notional, affordable_trade)
                    transaction_cost = abs(trade_notional) * cost_rate
                    new_cash = cash - trade_notional - transaction_cost
                shares += trade_notional / bar.open
                cash = max(0.0, new_cash)
                turnover = abs(trade_notional) / equity_at_open if equity_at_open > 0 else 0.0
                execution_price = bar.open
                total_cost += transaction_cost
                cumulative_turnover += turnover
                equity_after_trade = cash + shares * bar.open
                actual_weight_after = shares * bar.open / equity_after_trade if equity_after_trade > 0 else 0.0
                trades.append({
                    "signal_date": previous_bar.date,
                    "execution_date": bar.date,
                    "execution_price": bar.open,
                    "reason": signal.reason,
                    "signal_values": dict(signal.values),
                    "target_weight": round(target_weight, 8),
                    "pre_trade_weight": round(current_weight, 8),
                    "post_trade_weight": round(actual_weight_after, 8),
                    "trade_notional": round(trade_notional, 10),
                    "turnover": round(turnover, 10),
                    "transaction_cost": round(transaction_cost, 10),
                })

        equity = cash + shares * bar.close
        actual_weight = shares * bar.close / equity if equity > 0 else 0.0
        daily_return = equity / previous_equity - 1.0 if previous_equity > 0 else 0.0
        ledger.append({
            "date": bar.date,
            "signal_date": previous_bar.date if signal is not None else None,
            "execution_price": execution_price,
            "target_weight": round(target_weight, 8),
            "actual_weight": round(actual_weight, 8),
            "turnover": round(turnover, 10),
            "transaction_cost": round(transaction_cost, 10),
            "cash": round(cash, 10),
            "shares": round(shares, 12),
            "close": bar.close,
            "equity": round(equity, 10),
            "daily_return": round(daily_return, 12),
        })

    metrics = _metrics(
        [row["equity"] for row in ledger],
        config.trading_days_per_year,
        config.annual_risk_free_rate,
    )
    metrics.update({
        "start_date": ledger[0]["date"],
        "end_date": ledger[-1]["date"],
        "trade_count": len(trades),
        "cumulative_turnover": round(cumulative_turnover, 4),
        "total_transaction_cost": round(total_cost, 6),
        "cost_as_initial_capital_pct": round(total_cost / config.initial_cash * 100, 4),
        "average_target_weight_pct": round(mean(row["target_weight"] for row in ledger) * 100, 4),
        "average_actual_weight_pct": round(mean(row["actual_weight"] for row in ledger) * 100, 4),
    })
    return BacktestResult(asdict(config), metrics, ledger, trades)


def run_buy_and_hold(
    bars: Sequence[Bar],
    start_date: str,
    config: BacktestConfig = BacktestConfig(),
) -> BacktestResult:
    """从 ``start_date`` 的下一交易日开盘一次性买入并持有。"""
    validate_bars(bars)
    signal = Signal(start_date, 1.0, "Buy & Hold初始买入", {})
    return run_backtest(bars, {start_date: signal}, config)
