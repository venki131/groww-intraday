"""Tests for strategy signal generation."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from strategies.base import SignalType
from strategies.ema_crossover import EMACrossoverStrategy
from strategies.rsi_mean_reversion import RSIMeanReversionStrategy


def _make_crossover_df(fast_above: bool = True) -> pd.DataFrame:
    """
    Build minimal OHLCV DataFrame engineered to trigger a crossover.

    If fast_above=True  → prices trend UP  → bullish crossover eventually
    If fast_above=False → prices trend DOWN → bearish crossover eventually
    """
    from datetime import datetime, timedelta
    base = datetime(2023, 6, 1, 9, 15)
    rows = []
    # First 21 candles: flat (allow EMAs to initialize)
    price = 1000.0
    for i in range(21):
        rows.append({"timestamp": base + timedelta(minutes=i * 5),
                     "open": price, "high": price + 1, "low": price - 1,
                     "close": price, "volume": 10000})

    # Next 10 candles: strong trend to force crossover
    step = 10.0 if fast_above else -10.0
    for i in range(10):
        price += step
        rows.append({"timestamp": base + timedelta(minutes=(21 + i) * 5),
                     "open": price, "high": price + 1, "low": price - 1,
                     "close": price, "volume": 10000})
    return pd.DataFrame(rows)


def test_ema_strategy_requires_min_candles(ema_strategy: EMACrossoverStrategy) -> None:
    """Should raise ValueError if too few candles."""
    tiny_df = pd.DataFrame([
        {"timestamp": "2023-01-01", "open": 100, "high": 105,
         "low": 95, "close": 102, "volume": 1000}
    ])
    with pytest.raises(ValueError, match="candles"):
        ema_strategy.generate_signals("RELIANCE", tiny_df)


def test_ema_strategy_returns_list(
    ema_strategy: EMACrossoverStrategy,
    sample_candles_df: pd.DataFrame,
) -> None:
    """generate_signals must always return a list."""
    result = ema_strategy.generate_signals("RELIANCE", sample_candles_df)
    assert isinstance(result, list)


def test_ema_all_signals_are_buy_or_sell(
    ema_strategy: EMACrossoverStrategy,
    sample_candles_df: pd.DataFrame,
) -> None:
    signals = ema_strategy.generate_all_signals("RELIANCE", sample_candles_df)
    for s in signals:
        assert s.signal_type in {SignalType.BUY, SignalType.SELL}
        assert s.stop_loss is not None
        assert s.take_profit is not None
        assert s.ticker == "RELIANCE"


def test_ema_bullish_crossover_produces_buy() -> None:
    """Upward-trending candles must eventually produce a BUY signal."""
    strategy = EMACrossoverStrategy(fast_period=5, slow_period=10)
    df = _make_crossover_df(fast_above=True)
    signals = strategy.generate_all_signals("TEST", df)
    buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]
    assert len(buy_signals) > 0, "Expected at least one BUY from bullish crossover"


def test_ema_bearish_crossover_produces_sell() -> None:
    """Downward-trending candles must produce a SELL signal."""
    strategy = EMACrossoverStrategy(fast_period=5, slow_period=10)
    df = _make_crossover_df(fast_above=False)
    signals = strategy.generate_all_signals("TEST", df)
    sell_signals = [s for s in signals if s.signal_type == SignalType.SELL]
    assert len(sell_signals) > 0, "Expected at least one SELL from bearish crossover"


def test_ema_signal_has_valid_stop_loss_and_tp() -> None:
    strategy = EMACrossoverStrategy(fast_period=5, slow_period=10, stop_loss_pct=1.5, take_profit_pct=3.0)
    df = _make_crossover_df(fast_above=True)
    signals = strategy.generate_all_signals("TEST", df)
    for s in signals:
        if s.signal_type == SignalType.BUY:
            assert s.stop_loss < s.price, "Stop loss must be below entry for BUY"
            assert s.take_profit > s.price, "Take profit must be above entry for BUY"


def test_rsi_strategy_returns_list(
    rsi_strategy: RSIMeanReversionStrategy,
    sample_candles_df: pd.DataFrame,
) -> None:
    result = rsi_strategy.generate_signals("RELIANCE", sample_candles_df)
    assert isinstance(result, list)


def test_rsi_all_signals_valid(
    rsi_strategy: RSIMeanReversionStrategy,
    sample_candles_df: pd.DataFrame,
) -> None:
    signals = rsi_strategy.generate_all_signals("RELIANCE", sample_candles_df)
    for s in signals:
        assert s.signal_type in {SignalType.BUY, SignalType.SELL}
        assert 0.0 <= s.confidence <= 1.0
        assert s.ticker == "RELIANCE"


def test_strategy_validate_dataframe_missing_col(
    ema_strategy: EMACrossoverStrategy,
) -> None:
    """Missing 'volume' column must raise ValueError."""
    bad_df = pd.DataFrame([
        {"timestamp": "2023-01-01", "open": 100, "high": 110, "low": 90, "close": 105}
        for _ in range(30)
    ])
    with pytest.raises(ValueError, match="volume"):
        ema_strategy.validate_dataframe(bad_df)


def test_candles_to_dataframe(mock_broker) -> None:
    candles = mock_broker._candles.get("RELIANCE", [])
    df = EMACrossoverStrategy.candles_to_dataframe(candles)
    assert "close" in df.columns
    assert len(df) == len(candles)
    assert df["timestamp"].is_monotonic_increasing