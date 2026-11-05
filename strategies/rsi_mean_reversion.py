"""
RSI Mean Reversion Strategy.

Logic:
- BUY  when RSI crosses ABOVE oversold threshold (default 30) from below
- SELL when RSI crosses BELOW overbought threshold (default 70) from above
- Uses Wilder's smoothing (standard RSI calculation)

Default parameters:
    rsi_period   = 14
    oversold     = 30
    overbought   = 70
    stop_loss_pct    = 1.5%
    take_profit_pct  = 2.5%
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from config.logging_config import get_logger
from strategies.base import AbstractStrategy, Signal, SignalType

logger = get_logger(__name__)


class RSIMeanReversionStrategy(AbstractStrategy):
    """
    RSI-based mean reversion strategy for NSE intraday equities.

    Enters long when RSI recovers from oversold zone and
    enters short when RSI falls from overbought zone.

    Args:
        rsi_period: RSI lookback period (default 14).
        oversold: RSI level considered oversold (default 30).
        overbought: RSI level considered overbought (default 70).
        stop_loss_pct: Stop-loss percentage (default 1.5).
        take_profit_pct: Take-profit percentage (default 2.5).
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        stop_loss_pct: float = 1.5,
        take_profit_pct: float = 2.5,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        effective_params = {
            "rsi_period": rsi_period,
            "oversold": oversold,
            "overbought": overbought,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            **(params or {}),
        }
        super().__init__(name="rsi_mean_reversion", params=effective_params)

        self.rsi_period: int = int(effective_params["rsi_period"])
        self.oversold: float = float(effective_params["oversold"])
        self.overbought: float = float(effective_params["overbought"])
        self.stop_loss_pct: float = float(effective_params["stop_loss_pct"])
        self.take_profit_pct: float = float(effective_params["take_profit_pct"])

    def get_required_candle_count(self) -> int:
        """Need rsi_period + 2 candles to detect RSI crossover."""
        return self.rsi_period + 2

    @staticmethod
    def _compute_rsi(close: pd.Series, period: int) -> pd.Series:
        """
        Compute RSI using Wilder's exponential smoothing.

        Args:
            close: Series of close prices.
            period: RSI lookback period.

        Returns:
            Series of RSI values (0-100 range).
        """
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    def generate_signals(
        self,
        ticker: str,
        candles_df: pd.DataFrame,
    ) -> List[Signal]:
        """
        Generate RSI mean-reversion signals for the latest candle.

        Args:
            ticker: NSE symbol.
            candles_df: OHLCV DataFrame sorted ascending by timestamp.

        Returns:
            List containing at most one Signal.
        """
        self.validate_dataframe(candles_df)

        df = candles_df.copy()
        df["rsi"] = self._compute_rsi(df["close"], self.rsi_period)
        df["prev_rsi"] = df["rsi"].shift(1)

        latest = df.iloc[-1]
        signals: List[Signal] = []
        price = Decimal(str(round(latest["close"], 2)))

        rsi_now = latest["rsi"]
        rsi_prev = latest["prev_rsi"]

        # BUY: RSI crossing up through oversold
        if rsi_prev < self.oversold <= rsi_now:
            sl = price * Decimal(str(1 - self.stop_loss_pct / 100))
            tp = price * Decimal(str(1 + self.take_profit_pct / 100))
            signals.append(Signal(
                ticker=ticker,
                signal_type=SignalType.BUY,
                price=price,
                timestamp=latest["timestamp"],
                strategy_name=self.name,
                stop_loss=sl.quantize(Decimal("0.01")),
                take_profit=tp.quantize(Decimal("0.01")),
                confidence=min(1.0, (self.oversold - rsi_prev) / self.oversold),
                metadata={"rsi": round(rsi_now, 2), "prev_rsi": round(rsi_prev, 2)},
            ))
            logger.info(
                "RSI oversold recovery",
                ticker=ticker,
                rsi=round(rsi_now, 2),
                price=float(price),
            )

        # SELL: RSI crossing down through overbought
        elif rsi_prev > self.overbought >= rsi_now:
            sl = price * Decimal(str(1 + self.stop_loss_pct / 100))
            tp = price * Decimal(str(1 - self.take_profit_pct / 100))
            signals.append(Signal(
                ticker=ticker,
                signal_type=SignalType.SELL,
                price=price,
                timestamp=latest["timestamp"],
                strategy_name=self.name,
                stop_loss=sl.quantize(Decimal("0.01")),
                take_profit=tp.quantize(Decimal("0.01")),
                confidence=min(1.0, (rsi_prev - self.overbought) / (100 - self.overbought)),
                metadata={"rsi": round(rsi_now, 2), "prev_rsi": round(rsi_prev, 2)},
            ))
            logger.info(
                "RSI overbought reversal",
                ticker=ticker,
                rsi=round(rsi_now, 2),
                price=float(price),
            )

        return signals

    def generate_all_signals(
        self,
        ticker: str,
        candles_df: pd.DataFrame,
    ) -> List[Signal]:
        """
        Generate signals across all candles (backtest mode).

        Args:
            ticker: NSE symbol.
            candles_df: Full historical OHLCV DataFrame.

        Returns:
            All Signal objects in chronological order.
        """
        self.validate_dataframe(candles_df)

        df = candles_df.copy()
        df["rsi"] = self._compute_rsi(df["close"], self.rsi_period)
        df["prev_rsi"] = df["rsi"].shift(1)

        signals: List[Signal] = []

        for _, row in df.iterrows():
            if pd.isna(row["prev_rsi"]):
                continue

            price = Decimal(str(round(row["close"], 2)))
            rsi_now = row["rsi"]
            rsi_prev = row["prev_rsi"]

            if rsi_prev < self.oversold <= rsi_now:
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
                    metadata={"rsi": round(rsi_now, 2)},
                ))

            elif rsi_prev > self.overbought >= rsi_now:
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
                    metadata={"rsi": round(rsi_now, 2)},
                ))

        return signals