"""
Pytest fixtures shared across all test modules.

Provides:
- mock_broker: MockBroker with synthetic candle data
- ema_strategy: EMACrossoverStrategy with defaults
- rsi_strategy: RSIMeanReversionStrategy with defaults
- sample_candles_df: pandas DataFrame of 100 synthetic 5-min candles
- risk_manager: RiskManager with ₹10,000 capital
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from broker.mock import MockBroker
from risk.manager import RiskManager
from strategies.ema_crossover import EMACrossoverStrategy
from strategies.rsi_mean_reversion import RSIMeanReversionStrategy


@pytest.fixture
def mock_broker() -> MockBroker:
    """MockBroker with pre-loaded RELIANCE candles."""
    broker = MockBroker(
        initial_prices={"RELIANCE": Decimal("2500")},
        available_cash=Decimal("10000"),
    )
    broker.generate_candles("RELIANCE", count=100, base_price=Decimal("2500"))
    return broker


@pytest.fixture
def ema_strategy() -> EMACrossoverStrategy:
    return EMACrossoverStrategy(fast_period=9, slow_period=21)


@pytest.fixture
def rsi_strategy() -> RSIMeanReversionStrategy:
    return RSIMeanReversionStrategy(rsi_period=14)


@pytest.fixture
def sample_candles_df(mock_broker: MockBroker) -> pd.DataFrame:
    """Return 100 synthetic 5-min candles as DataFrame."""
    candles = mock_broker._candles.get("RELIANCE", [])
    return pd.DataFrame([
        {"timestamp": c.timestamp, "open": float(c.open), "high": float(c.high),
         "low": float(c.low), "close": float(c.close), "volume": c.volume}
        for c in candles
    ])


@pytest.fixture
def risk_manager() -> RiskManager:
    return RiskManager(capital=Decimal("10000"))