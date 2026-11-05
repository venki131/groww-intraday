"""
EMA Crossover Strategy.

Logic:
- BUY  when fast EMA crosses ABOVE slow EMA (bullish crossover)
- SELL when fast EMA crosses BELOW slow EMA (bearish crossover)
- Stop loss  : entry_price * (1 - stop_loss_pct)
- Take profit: entry_price * (1 + take_profit_pct)

Default parameters (from settings.yaml):
    fast_period  = 9
    slow_period  = 21
    stop_loss_pct    = 1.5%
    take_profit_pct  = 3.0%
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd

from config.logging_config import get_logger
from strategies.base import AbstractStrategy, Signal, SignalType

logger = get_logger(__name__)


class EMACrossoverStrategy(AbstractStrategy):
    """
    Exponential Moving Average crossover strategy.

    Generates BUY on bullish crossover and SELL on bearish crossover
    of fast and slow EMAs computed on 5-minute OHLCV candles.

    Args:
        fast_period: EMA period for fast line (default 9).
        slow_period: EMA period for slow line (default 21).
        stop_loss_pct: Stop-loss percentage below entry (default 1.5).
        take_profit_pct: Take-profit percentage above entry (default 3.0).
    """

    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
        stop_loss_pct: float = 1.5,
        take_profit_pct: float = 3.0,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        effective_params = {
            "fast_period": fast_period,
            "slow_period": slow_period,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            **(params or {}),
        }
        super().__init__(name="ema_crossover", params=effective_params)

        self.fast_period: int = int(effective_params["fast_period"])
        self.slow_period: int = int(effective_params["slow_period"])
        self.stop_loss_pct: float = float(effective_params["stop_loss_pct"])
        self.take_profit_pct: float = float(effective_params["take_profit_pct"])

    def get_required_candle_count(self) -> int:
        """Need at least slow_period + 1 candles to detect a crossover."""
        return self.slow_period + 1

    def generate_signals(
        self,
        ticker: str,
        candles_df: pd.DataFrame,
    ) -> List[Signal]:
        """
        Generate EMA crossover signals.

        Args:
            ticker: NSE symbol.
            candles_df: OHLCV DataFrame sorted ascending by timestamp.

        Returns:
            List of Signal objects. At most one signal per call
            (the signal for the latest completed candle).
        """
        self.validate_dataframe(candles_df)

        df = candles_df.copy()

        # Compute EMAs on close prices
        df["ema_fast"] = df["close"].ewm(span=self.fast_period, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_period, adjust=False).mean()

        # Detect crossover: fast crosses slow
        df["prev_fast"] = df["ema_fast"].shift(1)
        df["prev_slow"] = df["ema_slow"].shift(1)

        # Bullish crossover: fast was at or below slow, now strictly above
        df["bullish_cross"] = (
            (df["prev_fast"] <= df["prev_slow"]) &
            (df["ema_fast"] > df["ema_slow"])
        )

        # Bearish crossover: fast was at or above slow, now strictly below
        df["bearish_cross"] = (
            (df["prev_fast"] >= df["prev_slow"]) &
            (df["ema_fast"] < df["ema_slow"])
        )

        # Look at only the latest candle for a live/paper signal
        latest = df.iloc[-1]
        signals: List[Signal] = []

        entry_price = Decimal(str(round(latest["close"], 2)))
        ts = latest["timestamp"]

        if latest["bullish_cross"]:
            stop_loss = entry_price * Decimal(str(1 - self.stop_loss_pct / 100))
            take_profit = entry_price * Decimal(str(1 + self.take_profit_pct / 100))

            signal = Signal(
                ticker=ticker,
                signal_type=SignalType.BUY,
                price=entry_price,
                timestamp=ts,
                strategy_name=self.name,
                stop_loss=stop_loss.quantize(Decimal("0.01")),
                take_profit=take_profit.quantize(Decimal("0.01")),
                confidence=0.75,
                metadata={
                    "ema_fast": round(latest["ema_fast"], 4),
                    "ema_slow": round(latest["ema_slow"], 4),
                    "fast_period": self.fast_period,
                    "slow_period": self.slow_period,
                },
            )
            signals.append(signal)
            logger.info(
                "EMA bullish crossover",
                ticker=ticker,
                price=float(entry_price),
                ema_fast=round(latest["ema_fast"], 2),
                ema_slow=round(latest["ema_slow"], 2),
            )

        elif latest["bearish_cross"]:
            stop_loss = entry_price * Decimal(str(1 + self.stop_loss_pct / 100))
            take_profit = entry_price * Decimal(str(1 - self.take_profit_pct / 100))

            signal = Signal(
                ticker=ticker,
                signal_type=SignalType.SELL,
                price=entry_price,
                timestamp=ts,
                strategy_name=self.name,
                stop_loss=stop_loss.quantize(Decimal("0.01")),
                take_profit=take_profit.quantize(Decimal("0.01")),
                confidence=0.75,
                metadata={
                    "ema_fast": round(latest["ema_fast"], 4),
                    "ema_slow": round(latest["ema_slow"], 4),
                    "fast_period": self.fast_period,
                    "slow_period": self.slow_period,
                },
            )
            signals.append(signal)
            logger.info(
                "EMA bearish crossover",
                ticker=ticker,
                price=float(entry_price),
                ema_fast=round(latest["ema_fast"], 2),
                ema_slow=round(latest["ema_slow"], 2),
            )

        return signals

    def generate_all_signals(
        self,
        ticker: str,
        candles_df: pd.DataFrame,
    ) -> List[Signal]:
        """
        Generate signals for ALL candles in the DataFrame (for backtesting).

        Args:
            ticker: NSE symbol.
            candles_df: Full historical OHLCV DataFrame.

        Returns:
            List of all Signal objects across the entire dataset.
        """
        self.validate_dataframe(candles_df)

        df = candles_df.copy()
        df["ema_fast"] = df["close"].ewm(span=self.fast_period, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_period, adjust=False).mean()
        df["prev_fast"] = df["ema_fast"].shift(1)
        df["prev_slow"] = df["ema_slow"].shift(1)

        # Symmetric crossover: <= / >= to catch equal→diverge transitions
        df["bullish_cross"] = (
            (df["prev_fast"] <= df["prev_slow"]) & (df["ema_fast"] > df["ema_slow"])
        )
        df["bearish_cross"] = (
            (df["prev_fast"] >= df["prev_slow"]) & (df["ema_fast"] < df["ema_slow"])
        )

        signals: List[Signal] = []

        for _, row in df.iterrows():
            if pd.isna(row["prev_fast"]):
                continue

            price = Decimal(str(round(row["close"], 2)))

            if row["bullish_cross"]:
                sl = price * Decimal(str(1 - self.stop_loss_pct / 100))
                tp = price * Decimal(str(1 + self.take_profit_pct / 100))
                signals.append(Signal(
                    ticker=ticker,
                    signal_type=SignalType.BUY,
                    price=price,
                    timestamp=row["timestamp"],
                    strategy_name=self.name,
                    stop_loss=sl.quantize(Decimal("0.01")),
                    take_profit=tp.quantize(Decimal("0.01")),
                    metadata={
                        "ema_fast": round(row["ema_fast"], 4),
                        "ema_slow": round(row["ema_slow"], 4),
                    },
                ))
            elif row["bearish_cross"]:
                sl = price * Decimal(str(1 + self.stop_loss_pct / 100))
                tp = price * Decimal(str(1 - self.take_profit_pct / 100))
                signals.append(Signal(
                    ticker=ticker,
                    signal_type=SignalType.SELL,
                    price=price,
                    timestamp=row["timestamp"],
                    strategy_name=self.name,
                    stop_loss=sl.quantize(Decimal("0.01")),
                    take_profit=tp.quantize(Decimal("0.01")),
                    metadata={
                        "ema_fast": round(row["ema_fast"], 4),
                        "ema_slow": round(row["ema_slow"], 4),
                    },
                ))

        return signals