"""
Risk Management Module.

Enforces position sizing, daily loss limits, max open positions,
and per-trade risk constraints before any order is placed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from config.logging_config import get_logger
from strategies.base import Signal, SignalType

logger = get_logger(__name__)


@dataclass
class RiskCheckResult:
    """Result of a risk validation check."""

    approved: bool
    reason: str
    adjusted_quantity: int = 0
    adjusted_stop_loss: Optional[Decimal] = None

    def __bool__(self) -> bool:
        return self.approved


class RiskManager:
    """
    Pre-trade and intraday risk management engine.

    Validates:
    1. Max open positions
    2. Max daily loss
    3. Per-trade risk (% of capital)
    4. Max position size (% of capital)
    5. Stop-loss presence

    Args:
        capital: Total trading capital in INR.
        max_risk_per_trade_pct: Max loss per trade as % of capital.
        max_open_positions: Maximum simultaneous open positions.
        max_daily_loss_pct: Max daily drawdown as % of capital.
        max_position_size_pct: Max single position size as % of capital.
        stop_loss_pct: Default stop-loss if signal has none.
    """

    def __init__(
        self,
        capital: Decimal = Decimal("10000"),
        max_risk_per_trade_pct: float = 1.0,
        max_open_positions: int = 3,
        max_daily_loss_pct: float = 3.0,
        max_position_size_pct: float = 20.0,
        stop_loss_pct: float = 1.5,
    ) -> None:
        self.capital: Decimal = capital
        self.max_risk_per_trade_pct: float = max_risk_per_trade_pct
        self.max_open_positions: int = max_open_positions
        self.max_daily_loss_pct: float = max_daily_loss_pct
        self.max_position_size_pct: float = max_position_size_pct
        self.stop_loss_pct: float = stop_loss_pct

        # Runtime state
        self._open_positions: int = 0
        self._daily_pnl: Decimal = Decimal("0")
        self._daily_trades: int = 0

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def update_daily_pnl(self, pnl_delta: Decimal) -> None:
        """
        Update running daily P&L.

        Args:
            pnl_delta: Profit (positive) or loss (negative) in INR.
        """
        self._daily_pnl += pnl_delta
        logger.debug("Daily PnL updated", daily_pnl=float(self._daily_pnl))

    def open_position(self) -> None:
        """Increment open position counter."""
        self._open_positions += 1

    def close_position(self) -> None:
        """Decrement open position counter."""
        self._open_positions = max(0, self._open_positions - 1)

    def reset_daily(self) -> None:
        """Reset daily counters (call at start of each trading day)."""
        self._daily_pnl = Decimal("0")
        self._daily_trades = 0
        self._open_positions = 0
        logger.info("Risk manager daily state reset")

    # ------------------------------------------------------------------
    # Core validation
    # ------------------------------------------------------------------

    def validate_signal(
        self,
        signal: Signal,
        current_positions: Optional[List[str]] = None,
    ) -> RiskCheckResult:
        """
        Validate a strategy signal against all risk rules.

        Args:
            signal: Signal from strategy.
            current_positions: List of currently held tickers.

        Returns:
            RiskCheckResult with approved flag and computed quantity.
        """
        # --- Daily loss guard ---
        daily_loss_limit = self.capital * Decimal(str(self.max_daily_loss_pct / 100))
        if self._daily_pnl <= -daily_loss_limit:
            msg = (
                f"Daily loss limit hit: PnL={float(self._daily_pnl):.2f} "
                f">= limit={float(daily_loss_limit):.2f}"
            )
            logger.warning("Risk: daily loss limit", ticker=signal.ticker)
            return RiskCheckResult(approved=False, reason=msg)

        # --- Max open positions guard ---
        if self._open_positions >= self.max_open_positions:
            msg = f"Max open positions reached: {self._open_positions}/{self.max_open_positions}"
            logger.warning("Risk: max positions", ticker=signal.ticker)
            return RiskCheckResult(approved=False, reason=msg)

        # --- Duplicate position guard ---
        if current_positions and signal.ticker in current_positions:
            msg = f"Already have open position in {signal.ticker}"
            return RiskCheckResult(approved=False, reason=msg)

        # --- Compute stop-loss distance ---
        if signal.stop_loss:
            stop_loss = signal.stop_loss
        else:
            # Apply default stop-loss
            factor = Decimal(str(1 - self.stop_loss_pct / 100))
            stop_loss = (signal.price * factor).quantize(Decimal("0.01"))

        risk_per_share = abs(signal.price - stop_loss)
        if risk_per_share <= Decimal("0"):
            return RiskCheckResult(
                approved=False, reason="Stop-loss distance is zero or negative"
            )

        # --- Compute position size from risk budget ---
        risk_budget = self.capital * Decimal(str(self.max_risk_per_trade_pct / 100))
        raw_quantity = int(risk_budget / risk_per_share)

        # --- Apply max position size cap ---
        max_pos_value = self.capital * Decimal(str(self.max_position_size_pct / 100))
        max_qty_by_capital = int(max_pos_value / signal.price)
        quantity = min(raw_quantity, max_qty_by_capital)

        if quantity <= 0:
            return RiskCheckResult(
                approved=False,
                reason=(
                    f"Computed quantity is 0 for {signal.ticker} "
                    f"(risk_budget={float(risk_budget):.2f}, "
                    f"risk_per_share={float(risk_per_share):.2f})"
                ),
            )

        logger.info(
            "Risk check approved",
            ticker=signal.ticker,
            quantity=quantity,
            risk_budget=float(risk_budget),
            stop_loss=float(stop_loss),
        )

        return RiskCheckResult(
            approved=True,
            reason="All risk checks passed",
            adjusted_quantity=quantity,
            adjusted_stop_loss=stop_loss,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def daily_pnl(self) -> Decimal:
        """Current day's realized P&L."""
        return self._daily_pnl

    @property
    def open_positions_count(self) -> int:
        """Number of currently open positions."""
        return self._open_positions

    @property
    def is_trading_allowed(self) -> bool:
        """
        Return False if daily loss limit has been breached.

        Returns:
            True if safe to trade, False if daily loss limit hit.
        """
        daily_loss_limit = self.capital * Decimal(str(self.max_daily_loss_pct / 100))
        return self._daily_pnl > -daily_loss_limit