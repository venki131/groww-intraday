"""
SQLAlchemy ORM models for Groww Intraday Automation.

Tables:
- symbols          : Nifty 100 instrument metadata
- candles          : OHLCV price data (5-min)
- trades           : Paper / backtest trade records
- positions        : Open / closed position snapshots
- orders           : Order lifecycle records
- daily_pnl        : Per-symbol daily P&L summaries
- backtest_runs    : Backtest session metadata
- backtest_results : Per-trade results for a backtest run
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Symbol / Instrument
# ---------------------------------------------------------------------------


class Symbol(Base, UUIDMixin, TimestampMixin):
    """NSE equity instrument metadata (Nifty 100 universe)."""

    __tablename__ = "symbols"

    ticker: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False, default="NSE")
    segment: Mapped[str] = mapped_column(String(10), nullable=False, default="EQ")
    isin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.05"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    in_nifty100: Mapped[bool] = mapped_column(Boolean, default=True)

    candles: Mapped[List["Candle"]] = relationship("Candle", back_populates="symbol")
    trades: Mapped[List["Trade"]] = relationship("Trade", back_populates="symbol")
    positions: Mapped[List["Position"]] = relationship("Position", back_populates="symbol")

    def __repr__(self) -> str:
        return f"<Symbol {self.ticker}>"


# ---------------------------------------------------------------------------
# OHLCV Candles
# ---------------------------------------------------------------------------


class Candle(Base, TimestampMixin):
    """5-minute OHLCV candle data."""

    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vwap: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)

    symbol: Mapped["Symbol"] = relationship("Symbol", back_populates="candles")

    __table_args__ = (
        UniqueConstraint("ticker", "timestamp", "interval_minutes", name="uq_candle"),
        Index("ix_candle_ticker_ts", "ticker", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<Candle {self.ticker} @ {self.timestamp}>"


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class Order(Base, UUIDMixin, TimestampMixin):
    """Order lifecycle record (paper / backtest only)."""

    __tablename__ = "orders"

    broker_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(10), default="NSE")
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)  # MARKET | LIMIT | SL
    transaction_type: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY | SELL
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    trigger_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    # PENDING | OPEN | COMPLETE | CANCELLED | REJECTED
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="backtest")  # backtest | paper
    strategy_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    placed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    trades: Mapped[List["Trade"]] = relationship("Trade", back_populates="order")

    def __repr__(self) -> str:
        return f"<Order {self.transaction_type} {self.quantity} {self.ticker} [{self.status}]>"


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


class Trade(Base, UUIDMixin, TimestampMixin):
    """Executed trade record."""

    __tablename__ = "trades"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    symbol_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    brokerage: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    taxes: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    strategy_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="backtest")
    traded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="trades")
    symbol: Mapped["Symbol"] = relationship("Symbol", back_populates="trades")

    __table_args__ = (Index("ix_trade_ticker_date", "ticker", "traded_at"),)

    def __repr__(self) -> str:
        return f"<Trade {self.transaction_type} {self.quantity} {self.ticker} @ {self.price}>"


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


class Position(Base, UUIDMixin, TimestampMixin):
    """Open or closed position snapshot."""

    __tablename__ = "positions"

    symbol_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    average_buy_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    unrealised_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    realised_pnl: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    take_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    strategy_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="backtest")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    symbol: Mapped["Symbol"] = relationship("Symbol", back_populates="positions")

    def __repr__(self) -> str:
        return f"<Position {self.ticker} qty={self.quantity} pnl={self.realised_pnl}>"


# ---------------------------------------------------------------------------
# Daily P&L
# ---------------------------------------------------------------------------


class DailyPnL(Base, UUIDMixin, TimestampMixin):
    """Aggregated daily profit & loss per symbol."""

    __tablename__ = "daily_pnl"

    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    gross_pnl: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    brokerage: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    strategy_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="backtest")

    __table_args__ = (
        UniqueConstraint("trade_date", "ticker", "strategy_name", "mode", name="uq_daily_pnl"),
    )

    def __repr__(self) -> str:
        return f"<DailyPnL {self.ticker} {self.trade_date} net={self.net_pnl}>"


# ---------------------------------------------------------------------------
# Backtest Sessions
# ---------------------------------------------------------------------------


class BacktestRun(Base, UUIDMixin, TimestampMixin):
    """Metadata for a single backtest run."""

    __tablename__ = "backtest_runs"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    universe: Mapped[str] = mapped_column(String(50), default="NIFTY100")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    final_capital: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    total_return_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    cagr_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    sharpe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    win_rate_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    parameters: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON blob
    status: Mapped[str] = mapped_column(String(20), default="running")
    # running | completed | failed

    results: Mapped[List["BacktestResult"]] = relationship(
        "BacktestResult", back_populates="run"
    )

    def __repr__(self) -> str:
        return f"<BacktestRun {self.name} [{self.status}]>"


class BacktestResult(Base, UUIDMixin, TimestampMixin):
    """Individual trade result within a backtest run."""

    __tablename__ = "backtest_results"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    net_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # stop_loss | take_profit | signal | eod

    run: Mapped["BacktestRun"] = relationship("BacktestRun", back_populates="results")

    def __repr__(self) -> str:
        return f"<BacktestResult {self.ticker} pnl={self.net_pnl}>"