"""Tests for BacktestEngine and BacktestReport."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backtesting.engine import BacktestEngine, BacktestReport
from broker.mock import MockBroker
from strategies.ema_crossover import EMACrossoverStrategy
from strategies.rsi_mean_reversion import RSIMeanReversionStrategy


def _build_engine(strategy=None, capital=Decimal("10000")) -> BacktestEngine:
    return BacktestEngine(
        strategy=strategy or EMACrossoverStrategy(fast_period=5, slow_period=10),
        capital=capital,
        commission_pct=0.03,
        slippage_pct=0.01,
    )


def test_backtest_runs_without_error(sample_candles_df) -> None:
    engine = _build_engine()
    report = engine.run(ticker="RELIANCE", candles_df=sample_candles_df)
    assert isinstance(report, BacktestReport)


def test_backtest_report_has_correct_ticker(sample_candles_df) -> None:
    report = _build_engine().run(ticker="RELIANCE", candles_df=sample_candles_df)
    assert report.ticker == "RELIANCE"
    assert report.strategy_name == "ema_crossover"


def test_backtest_initial_capital_preserved(sample_candles_df) -> None:
    report = _build_engine(capital=Decimal("15000")).run("RELIANCE", sample_candles_df)
    assert report.initial_capital == Decimal("15000")


def test_backtest_total_return_is_float(sample_candles_df) -> None:
    report = _build_engine().run("RELIANCE", sample_candles_df)
    assert isinstance(report.total_return_pct, float)


def test_backtest_win_rate_in_valid_range(sample_candles_df) -> None:
    report = _build_engine().run("RELIANCE", sample_candles_df)
    assert 0.0 <= report.win_rate_pct <= 100.0


def test_backtest_winning_plus_losing_equals_total(sample_candles_df) -> None:
    report = _build_engine().run("RELIANCE", sample_candles_df)
    assert report.winning_trades + report.losing_trades == report.total_trades


def test_backtest_max_drawdown_non_negative(sample_candles_df) -> None:
    report = _build_engine().run("RELIANCE", sample_candles_df)
    assert report.max_drawdown_pct >= 0.0


def test_backtest_to_dict_has_required_keys(sample_candles_df) -> None:
    report = _build_engine().run("RELIANCE", sample_candles_df)
    d = report.to_dict()
    for key in ["strategy_name", "ticker", "total_trades", "win_rate_pct",
                "total_return_pct", "max_drawdown_pct", "sharpe_ratio"]:
        assert key in d, f"Missing key: {key}"


def test_backtest_pnl_sum_matches_capital_change(sample_candles_df) -> None:
    report = _build_engine().run("RELIANCE", sample_candles_df)
    # final_capital = initial + sum(net_pnls) approximately (minus rounding)
    expected = report.initial_capital + report.total_pnl
    assert abs(report.final_capital - expected) < Decimal("1.00")


def test_backtest_with_rsi_strategy(sample_candles_df) -> None:
    engine = BacktestEngine(
        strategy=RSIMeanReversionStrategy(rsi_period=14),
        capital=Decimal("10000"),
    )
    report = engine.run("RELIANCE", sample_candles_df)
    assert isinstance(report, BacktestReport)
    assert report.total_return_pct is not None


def test_backtest_commission_reduces_pnl(sample_candles_df) -> None:
    """Higher commission must result in lower final capital."""
    low_comm = BacktestEngine(
        strategy=EMACrossoverStrategy(fast_period=5, slow_period=10),
        capital=Decimal("10000"), commission_pct=0.01,
    ).run("RELIANCE", sample_candles_df)

    high_comm = BacktestEngine(
        strategy=EMACrossoverStrategy(fast_period=5, slow_period=10),
        capital=Decimal("10000"), commission_pct=0.5,
    ).run("RELIANCE", sample_candles_df)

    if low_comm.total_trades > 0:
        assert low_comm.total_commission < high_comm.total_commission


def test_backtest_summary_contains_header(sample_candles_df) -> None:
    report = _build_engine().run("RELIANCE", sample_candles_df)
    summary = report.summary()
    assert "BACKTEST REPORT" in summary
    assert "Win Rate" in summary