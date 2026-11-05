"""
Abstract Strategy Base Class.

All trading strategies inherit from AbstractStrategy.
Strategies receive candle data and return Signal objects.
They must NOT contain broker or order placement logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd


class SignalType(str, Enum):
    """Trading signal direction."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    EXIT = "EXIT"


@dataclass
class Signal:
    """
    Trading signal emitted by a strategy.

    Attributes:
        ticker: NSE symbol.
        signal_type: BUY / SELL / HOLD / EXIT.
        price: Suggested entry/exit price.
        stop_loss: Suggested stop-loss price.
        take_profit: Suggested take-profit target.
        confidence: Signal confidence 0.0 - 1.0.
        timestamp: When the signal was generated.
        strategy_name: Name of the emitting strategy.
        metadata: Additional strategy-specific data.
    """

    ticker: str
    signal_type: SignalType
    price: Decimal
    timestamp: datetime
    strategy_name: str
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """Return True if signal warrants an order (not HOLD)."""
        return self.signal_type in {SignalType.BUY, SignalType.SELL, SignalType.EXIT}

    def __repr__(self) -> str:
        return (
            f"<Signal {self.signal_type.value} {self.ticker} "
            f"@ {self.price} sl={self.stop_loss} tp={self.take_profit}>"
        )


class AbstractStrategy(ABC):
    """
    Abstract base for all intraday strategies.

    Strategies are pure functions over price data - they:
    - Receive a DataFrame of OHLCV candles
    - Return a list of Signal objects
    - Do NOT place orders
    - Do NOT call the broker directly

    Args:
        name: Human-readable strategy name.
        params: Strategy-specific hyperparameters.
    """

    def __init__(self, name: str, params: Optional[Dict[str, Any]] = None) -> None:
        self.name: str = name
        self.params: Dict[str, Any] = params or {}

    @abstractmethod
    def generate_signals(
        self,
        ticker: str,
        candles_df: pd.DataFrame,
    ) -> List[Signal]:
        """
        Generate trading signals from OHLCV candle data.

        The DataFrame MUST have columns:
            timestamp, open, high, low, close, volume

        Args:
            ticker: NSE symbol being analyzed.
            candles_df: DataFrame of OHLCV candles ordered by timestamp ascending.

        Returns:
            List of Signal objects. Empty list = no action.
        """
        ...

    @abstractmethod
    def get_required_candle_count(self) -> int:
        """
        Minimum number of candles required before generating signals.

        Returns:
            Integer minimum candle count.
        """
        ...

    def validate_dataframe(self, df: pd.DataFrame) -> None:
        """
        Validate that the candle DataFrame has required columns.

        Args:
            df: Input DataFrame.

        Raises:
            ValueError: If required columns are missing.
        """
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"Strategy '{self.name}': DataFrame missing columns: {missing}"
            )
        if len(df) < self.get_required_candle_count():
            raise ValueError(
                f"Strategy '{self.name}': Need at least "
                f"{self.get_required_candle_count()} candles, got {len(df)}"
            )

    @staticmethod
    def candles_to_dataframe(candles: list) -> pd.DataFrame:
        """
        Convert a list of broker Candle objects to a pandas DataFrame.

        Args:
            candles: List of broker.base.Candle objects.

        Returns:
            DataFrame with float columns for numeric computation.
        """
        rows = [
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": c.volume,
            }
            for c in candles
        ]
        df = pd.DataFrame(rows)
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def __repr__(self) -> str:
        return f"<Strategy {self.name} params={self.params}>"