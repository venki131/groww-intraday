"""
Market Data ORM Models.

New tables for Nifty 100 data collection:
- instruments        : Detailed instrument metadata with Groww identifiers
- index_membership   : Historical index constituent snapshots (anti-survivorship-bias)
- candles_5m         : Dedicated 5-minute OHLCV table with data-quality flags
- data_download_jobs : Download job tracking and progress

These tables extend (not replace) the existing symbols/candles tables.
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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Instruments (Groww-enriched instrument metadata)
# ---------------------------------------------------------------------------


class Instrument(Base, UUIDMixin, TimestampMixin):
    """
    NSE equity instrument with Groww API identifiers and NSE metadata.

    Distinct from Symbol (which is the trading-engine view); this is the
    data-collection / universe-management view.
    """

    __tablename__ = "instruments"

    ticker: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    isin: Mapped[Optional[str]] = mapped_column(String(12), unique=True, nullable=True, index=True)
    groww_symbol: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )  # e.g. "NSE-RELIANCE"
    exchange: Mapped[str] = mapped_column(String(10), nullable=False, default="NSE")
    segment: Mapped[str] = mapped_column(String(10), nullable=False, default="EQ")
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.05"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    memberships: Mapped[List["IndexMembership"]] = relationship(
        "IndexMembership", back_populates="instrument"
    )
    candles: Mapped[List["Candle5m"]] = relationship("Candle5m", back_populates="instrument")
    download_jobs: Mapped[List["DataDownloadJob"]] = relationship(
        "DataDownloadJob", back_populates="instrument"
    )

    def __repr__(self) -> str:
        return f"<Instrument {self.ticker} ({self.groww_symbol})>"


# ---------------------------------------------------------------------------
# Index Membership (historical constituent snapshots)
# ---------------------------------------------------------------------------


class IndexMembership(Base, UUIDMixin, TimestampMixin):
    """
    Historical record of which instruments were members of an index.

    Enables anti-survivorship-bias backtesting: use get_members(as_of_date)
    to retrieve only stocks that were IN the index on the backtest date.

    effective_to=NULL means the stock is CURRENTLY in the index.
    """

    __tablename__ = "index_membership"

    index_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # NULL = still active member
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="NSE_OFFICIAL")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    instrument: Mapped["Instrument"] = relationship("Instrument", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint(
            "index_name", "ticker", "effective_from", name="uq_index_membership"
        ),
        Index("ix_membership_index_from", "index_name", "effective_from"),
        Index("ix_membership_index_to", "index_name", "effective_to"),
    )

    def __repr__(self) -> str:
        to = self.effective_to or "present"
        return f"<IndexMembership {self.index_name}:{self.ticker} {self.effective_from}→{to}>"


# ---------------------------------------------------------------------------
# Candles 5m (dedicated high-quality 5-minute OHLCV store)
# ---------------------------------------------------------------------------


class Candle5m(Base, TimestampMixin):
    """
    5-minute OHLCV candle with UTC timestamps and data-quality flags.

    Separated from the generic `candles` table for:
    - Partitioning by ticker/date range
    - Quality tracking (zero volume, missing, interpolated)
    - Source and retrieval metadata
    """

    __tablename__ = "candles_5m"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Always stored as UTC (normalized from IST on ingestion)
    timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vwap: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)

    # Data quality flags
    is_zero_volume: Mapped[bool] = mapped_column(Boolean, default=False)
    is_interpolated: Mapped[bool] = mapped_column(Boolean, default=False)
    # True = gap-filled candle (not from original API)
    has_ohlc_error: Mapped[bool] = mapped_column(Boolean, default=False)
    # True = high<low or close outside [low,high] etc.

    # Provenance
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="groww_api")
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    instrument: Mapped["Instrument"] = relationship("Instrument", back_populates="candles")

    __table_args__ = (
        UniqueConstraint("ticker", "timestamp_utc", name="uq_candle5m"),
        Index("ix_candle5m_ticker_ts", "ticker", "timestamp_utc"),
        Index("ix_candle5m_quality", "ticker", "is_zero_volume", "has_ohlc_error"),
    )

    def __repr__(self) -> str:
        return f"<Candle5m {self.ticker} @ {self.timestamp_utc}>"


# ---------------------------------------------------------------------------
# Data Download Jobs
# ---------------------------------------------------------------------------


class DataDownloadJob(Base, UUIDMixin, TimestampMixin):
    """
    Tracks historical candle download jobs for observability and retry.

    A job can cover a single ticker or an entire index (ticker=NULL,
    index_name set). Status transitions:
        pending → running → completed | failed | partial
    """

    __tablename__ = "data_download_jobs"

    instrument_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
    )
    ticker: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    index_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Set for bulk index downloads (ticker=NULL, index_name="NIFTY100")

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=5)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    # pending | running | completed | failed | partial

    candles_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    candles_expected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    candles_skipped_duplicates: Mapped[int] = mapped_column(Integer, default=0)
    candles_rejected_quality: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    instrument: Mapped[Optional["Instrument"]] = relationship(
        "Instrument", back_populates="download_jobs"
    )

    __table_args__ = (
        Index("ix_job_ticker_dates", "ticker", "start_date", "end_date"),
        Index("ix_job_status", "status"),
    )

    def __repr__(self) -> str:
        label = self.ticker or self.index_name or "?"
        return f"<DataDownloadJob {label} {self.start_date}→{self.end_date} [{self.status}]>"