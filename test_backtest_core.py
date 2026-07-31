#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest

from backtest_core import BacktestConfig, Bar, Signal, run_backtest, run_buy_and_hold, validate_bars


def sample_bars():
    return [
        Bar("20260101", 100, 101, 99, 100, 1000),
        Bar("20260102", 110, 121, 109, 120, 1000),
        Bar("20260105", 130, 141, 129, 140, 1000),
        Bar("20260106", 140, 141, 139, 140, 1000),
    ]


class BacktestCoreTests(unittest.TestCase):
    def test_t_signal_executes_next_open(self):
        bars = sample_bars()
        signal = Signal("20260101", 1.0, "test", {"x": 1.0})
        result = run_backtest(bars, {signal.date: signal})
        self.assertEqual(result.trades[0]["signal_date"], "20260101")
        self.assertEqual(result.trades[0]["execution_date"], "20260102")
        self.assertEqual(result.trades[0]["execution_price"], 110)
        self.assertAlmostEqual(result.ledger[1]["equity"], 120 / 110 * 100, places=8)

    def test_signal_does_not_capture_previous_overnight_gap(self):
        bars = sample_bars()
        signal = Signal("20260101", 1.0, "test", {})
        result = run_backtest(bars, {signal.date: signal})
        # 首日收盘100到次日开盘110的跳空发生在成交之前，策略不应获利。
        self.assertAlmostEqual(result.trades[0]["trade_notional"], 100.0, places=8)
        self.assertAlmostEqual(result.ledger[1]["equity"], 120 / 110 * 100, places=8)

    def test_transaction_cost_is_charged_on_one_way_notional(self):
        bars = sample_bars()
        signal = Signal("20260101", 0.5, "test", {})
        config = BacktestConfig(transaction_cost_bps=100.0)
        result = run_backtest(bars, {signal.date: signal}, config)
        trade = result.trades[0]
        self.assertAlmostEqual(trade["trade_notional"], 50.0, places=8)
        self.assertAlmostEqual(trade["transaction_cost"], 0.5, places=8)
        expected_equity = 49.5 + 50.0 / 110.0 * 120.0
        self.assertAlmostEqual(result.ledger[1]["equity"], expected_equity, places=8)

    def test_rebalance_band_blocks_small_trade(self):
        bars = sample_bars()
        signals = {
            "20260101": Signal("20260101", 0.5, "first", {}),
            "20260102": Signal("20260102", 0.51, "small", {}),
        }
        config = BacktestConfig(rebalance_band=0.10, rebalance_on_target_change_only=False)
        result = run_backtest(bars, signals, config)
        self.assertEqual(len(result.trades), 1)

    def test_same_target_does_not_force_daily_rebalance(self):
        bars = sample_bars()
        signals = {
            "20260101": Signal("20260101", 0.5, "first", {}),
            "20260102": Signal("20260102", 0.5, "same", {}),
            "20260105": Signal("20260105", 0.5, "same", {}),
        }
        result = run_backtest(bars, signals)
        self.assertEqual(len(result.trades), 1)

    def test_buy_and_hold_uses_next_open(self):
        bars = sample_bars()
        result = run_buy_and_hold(bars, "20260101")
        self.assertEqual(result.trades[0]["execution_date"], "20260102")
        self.assertAlmostEqual(result.ledger[-1]["equity"], 140 / 110 * 100, places=8)

    def test_invalid_bar_order_is_rejected(self):
        bars = sample_bars()
        bars[2] = Bar("20260101", 130, 141, 129, 140, 1000)
        with self.assertRaises(ValueError):
            validate_bars(bars)

    def test_invalid_ohlc_is_rejected(self):
        bars = sample_bars()
        bars[1] = Bar("20260102", 110, 108, 109, 120, 1000)
        with self.assertRaises(ValueError):
            validate_bars(bars)


if __name__ == "__main__":
    unittest.main(verbosity=2)
