"""
Backtesting Engine.

Event-driven backtester that:
- Replays historical 5-min OHLCV candles
- Runs strategy signals through risk manager
- Simulates fills with configurable slippage + commission
- Tracks equity curve, positions, and trade log
- Produces a comprehensive BacktestReport

Usage:
    engine = BacktestEngine(
        strategy=EMACrossoverStrategy(),
        capital=Decimal("10000"),
        commission_pct=0.03,
        slippage_pct=0.01,
    )
    report = engine.run(ticker="RELIANCE", candles_df=df)
    print(report.summary())
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd

from config.logging_config import get_logger
from risk.manager import RiskManager
from strategies.base import AbstractStrategy, Signal, SignalType

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class BacktestTrade:
    """A single completed round-trip trade in a backtest."""

    ticker: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: int
    gross_pnl: Decimal
    commission: Decimal
    net_pnl: Decimal
    exit_reason: str  # stop_loss | take_profit | signal | eod


@dataclass
class OpenPosition:
    """An open position during backtest replay."""

    ticker: str
    entry_time: datetime
    entry_price: Decimal
    quantity: int
    stop_loss: Decimal
    take_profit: Decimal
    signal: Signal


@dataclass
class BacktestReport:
    """
    Comprehensive backtest result report.

    Attributes:
        strategy_name: Name of the strategy tested.
        ticker: Symbol tested.
        initial_capital: Starting capital.
        final_capital: Ending capital.
        trades: All completed trades.
        equity_curve: Time-series of portfolio value.
        commission_pct: Commission rate used.
        slippage_pct: Slippage rate used.
    """

    strategy_name: str
    ticker: str
    initial_capital: Decimal
    final_capital: Decimal
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    commission_pct: float = 0.03
    slippage_pct: float = 0.01

    # --- Computed metrics ---

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.trades if t.net_pnl > 0)

    @property
    def losing_trades(self) -> int:
        return sum(1 for t in self.trades if t.net_pnl <= 0)

    @property
    def win_rate_pct(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return round(self.winning_trades / self.total_trades * 100, 2)

    @property
    def total_return_pct(self) -> float:
        return round(
            float((self.final_capital - self.initial_capital) / self.initial_capital * 100), 2
        )

    @property
    def total_pnl(self) -> Decimal:
        return sum((t.net_pnl for t in self.trades), Decimal("0"))

    @property
    def gross_pnl(self) -> Decimal:
        return sum((t.gross_pnl for t in self.trades), Decimal("0"))

    @property
    def total_commission(self) -> Decimal:
        return sum((t.commission for t in self.trades), Decimal("0"))

    @property
    def average_pnl(self) -> Decimal:
        if not self.trades:
            return Decimal("0")
        return self.total_pnl / len(self.trades)

    @property
    def max_drawdown_pct(self) -> float:
        """Maximum peak-to-trough drawdown percentage."""
        if not self.equity_curve:
            return 0.0
        values = [e["equity"] for e in self.equity_curve]
        peak = values[0]
        max_dd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 2)

    @property
    def sharpe_ratio(self) -> float:
        """Annualized Sharpe ratio (assumes 252 trading days, 75 candles/day)."""
        if len(self.trades) < 2:
            return 0.0
        pnls = [float(t.net_pnl) for t in self.trades]
        mean = sum(pnls) / len(pnls)
        variance = sum((p - mean) ** 2 for p in pnls) / len(pnls)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        # Annualize: sqrt(252 * 75 / avg_holding_candles)
        return round(mean / std * math.sqrt(len(pnls)), 2)

    def summary(self) -> str:
        """Return a formatted text summary of backtest results."""
        lines = [
            "=" * 60,
            f"BACKTEST REPORT: {self.strategy_name} | {self.ticker}",
            "=" * 60,
            f"  Initial Capital  : ₹{float(self.initial_capital):,.2f}",
            f"  Final Capital    : ₹{float(self.final_capital):,.2f}",
            f"  Total Return     : {self.total_return_pct:+.2f}%",
            f"  Total PnL        : ₹{float(self.total_pnl):+,.2f}",
            f"  Commission paid  : ₹{float(self.total_commission):,.2f}",
            f"  Total Trades     : {self.total_trades}",
            f"  Win Rate         : {self.win_rate_pct:.1f}%",
            f"  Winning Trades   : {self.winning_trades}",
            f"  Losing Trades    : {self.losing_trades}",
            f"  Max Drawdown     : {self.max_drawdown_pct:.2f}%",
            f"  Sharpe Ratio     : {self.sharpe_ratio:.2f}",
            "=" * 60,
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize report to dictionary for storage/API responses."""
        return {
            "strategy_name": self.strategy_name,
            "ticker": self.ticker,
            "initial_capital": float(self.initial_capital),
            "final_capital": float(self.final_capital),
            "total_return_pct": self.total_return_pct,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": self.win_rate_pct,
            "total_pnl": float(self.total_pnl),
            "gross_pnl": float(self.gross_pnl),
            "total_commission": float(self.total_commission),
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "commission_pct": self.commission_pct,
            "slippage_pct": self.slippage_pct,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """
    Event-driven backtesting engine for intraday equity strategies.

    Args:
        strategy: Strategy instance implementing AbstractStrategy.
        capital: Initial capital in INR.
        commission_pct: Per-trade commission as percentage (e.g. 0.03 = 0.03%).
        slippage_pct: Per-trade slippage as percentage (e.g. 0.01 = 0.01%).
        risk_manager: Optional RiskManager; created with defaults if None.
    """

    def __init__(
        self,
        strategy: AbstractStrategy,
        capital: Decimal = Decimal("10000"),
        commission_pct: float = 0.03,
        slippage_pct: float = 0.01,
        risk_manager: Optional[RiskManager] = None,
    ) -> None:
        self.strategy = strategy
        self.initial_capital = capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.risk_manager = risk_manager or RiskManager(capital=capital)

    def run(
        self,
        ticker: str,
        candles_df: pd.DataFrame,
    ) -> BacktestReport:
        """
        Run the backtest over the full candle history.

        Args:
            ticker: NSE symbol.
            candles_df: OHLCV DataFrame sorted ascending by timestamp.

        Returns:
            BacktestReport with all metrics.
        """
        logger.info(
            "Backtest started",
            ticker=ticker,
            strategy=self.strategy.name,
            candles=len(candles_df),
        )

        # Get all signals across dataset
        signals: List[Signal] = self.strategy.generate_all_signals(ticker, candles_df)

        capital = self.initial_capital
        trades: List[BacktestTrade] = []
        equity_curve: List[Dict[str, Any]] = []
        open_pos: Optional[OpenPosition] = None

        self.risk_manager.reset_daily()

        for signal in signals:
            # ----- Exit logic -----
            if open_pos is not None:
                # Find the candle at signal time for exit price
                exit_row = candles_df[candles_df["timestamp"] <= signal.timestamp]
                if exit_row.empty:
                    continue
                candle_close = Decimal(str(exit_row.iloc[-1]["close"]))

                should_exit = False
                exit_reason = "signal"

                # Check stop-loss
                if candle_close <= open_pos.stop_loss:
                    exit_price = open_pos.stop_loss
                    should_exit = True
                    exit_reason = "stop_loss"

                # Check take-profit
                elif candle_close >= open_pos.take_profit:
                    exit_price = open_pos.take_profit
                    should_exit = True
                    exit_reason = "take_profit"

                # Exit on opposite signal
                elif signal.signal_type == SignalType.SELL:
                    exit_price = signal.price
                    should_exit = True
                    exit_reason = "signal"

                if should_exit:
                    trade = self._close_trade(
                        pos=open_pos,
                        exit_price=exit_price if exit_reason != "signal" else signal.price,
                        exit_time=signal.timestamp,
                        exit_reason=exit_reason,
                    )
                    trades.append(trade)
                    capital += trade.net_pnl
                    self.risk_manager.update_daily_pnl(trade.net_pnl)
                    self.risk_manager.close_position()
                    open_pos = None

                    equity_curve.append({
                        "timestamp": signal.timestamp,
                        "equity": float(capital),
                        "trade_pnl": float(trade.net_pnl),
                    })

            # ----- Entry logic -----
            if open_pos is None and signal.signal_type == SignalType.BUY:
                if not self.risk_manager.is_trading_allowed:
                    logger.warning("Trading halted: daily loss limit", ticker=ticker)
                    continue

                risk_result = self.risk_manager.validate_signal(signal)
                if not risk_result.approved:
                    continue

                quantity = risk_result.adjusted_quantity
                stop_loss = risk_result.adjusted_stop_loss or signal.stop_loss
                take_profit = signal.take_profit or (
                    signal.price * Decimal("1.03")
                )

                # Apply slippage to entry
                entry_price = signal.price * Decimal(str(1 + self.slippage_pct / 100))
                entry_price = entry_price.quantize(Decimal("0.01"))

                open_pos = OpenPosition(
                    ticker=ticker,
                    entry_time=signal.timestamp,
                    entry_price=entry_price,
                    quantity=quantity,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    signal=signal,
                )
                self.risk_manager.open_position()
                logger.debug(
                    "Backtest position opened",
                    ticker=ticker,
                    entry=float(entry_price),
                    qty=quantity,
                )

        # --- Close any remaining open position at end of data (EOD) ---
        if open_pos is not None and not candles_df.empty:
            last_close = Decimal(str(candles_df.iloc[-1]["close"]))
            last_time = candles_df.iloc[-1]["timestamp"]
            trade = self._close_trade(
                pos=open_pos,
                exit_price=last_close,
                exit_time=last_time,
                exit_reason="eod",
            )
            trades.append(trade)
            capital += trade.net_pnl
            equity_curve.append({
                "timestamp": last_time,
                "equity": float(capital),
                "trade_pnl": float(trade.net_pnl),
            })

        report = BacktestReport(
            strategy_name=self.strategy.name,
            ticker=ticker,
            initial_capital=self.initial_capital,
            final_capital=capital,
            trades=trades,
            equity_curve=equity_curve,
            commission_pct=self.commission_pct,
            slippage_pct=self.slippage_pct,
        )

        logger.info(
            "Backtest completed",
            ticker=ticker,
            trades=report.total_trades,
            win_rate=report.win_rate_pct,
            total_return=report.total_return_pct,
        )
        return report

    def _close_trade(
        self,
        pos: OpenPosition,
        exit_price: Decimal,
        exit_time: datetime,
        exit_reason: str,
    ) -> BacktestTrade:
        """
        Calculate P&L for closing a position.

        Args:
            pos: The open position being closed.
            exit_price: Price at which position was closed.
            exit_time: Timestamp of exit.
            exit_reason: Reason string.

        Returns:
            Completed BacktestTrade.
        """
        # Apply slippage to exit (unfavorable direction)
        slipped_exit = exit_price * Decimal(str(1 - self.slippage_pct / 100))
        slipped_exit = slipped_exit.quantize(Decimal("0.01"))

        gross_pnl = (slipped_exit - pos.entry_price) * pos.quantity

        # Commission on both legs
        entry_value = pos.entry_price * pos.quantity
        exit_value = slipped_exit * pos.quantity
        commission = (entry_value + exit_value) * Decimal(str(self.commission_pct / 100))

        net_pnl = gross_pnl - commission

        return BacktestTrade(
            ticker=pos.ticker,
            entry_time=pos.entry_time,
            exit_time=exit_time,
            entry_price=pos.entry_price,
            exit_price=slipped_exit,
            quantity=pos.quantity,
            gross_pnl=gross_pnl.quantize(Decimal("0.01")),
            commission=commission.quantize(Decimal("0.01")),
            net_pnl=net_pnl.quantize(Decimal("0.01")),
            exit_reason=exit_reason,
        )