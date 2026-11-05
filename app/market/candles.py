"""
Candle data layer: validation, gap detection, storage, and download orchestration.

Modules
-------
- DataQualityIssue      — single data quality finding
- DataQualityReport     — aggregated quality summary for a ticker/date range
- validate_candles()    — pure function; flags quality issues in a DataFrame
- detect_missing_intervals() — pure function; returns missing 5-min slots
- CandleStore           — async CRUD over the candles_5m table
- CandleDownloader      — orchestrates chunked downloads + quality checks

UTC Normalization
-----------------
All timestamps stored as UTC in candles_5m.timestamp_utc.
Input DataFrames from Groww API arrive in IST (Asia/Kolkata, UTC+5:30).
normalize_to_utc() converts them before storage.

NSE Session
-----------
09:15–15:30 IST = 75 five-minute slots per trading day.
Slot timestamps (IST): 09:15, 09:20, … 15:25  (open of each 5-min bar)

Data Quality Flags
------------------
Per-candle flags stored in candles_5m:
  is_zero_volume   — volume == 0 (illiquid / market-halted candle)
  is_interpolated  — candle was gap-filled (not from raw API)
  has_ohlc_error   — open/high/low/close consistency violated
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

# NSE session times (IST)
_NSE_OPEN_H, _NSE_OPEN_M = 9, 15
_NSE_CLOSE_H, _NSE_CLOSE_M = 15, 30
_INTERVAL_MINUTES = 5
_SLOTS_PER_DAY = 75  # (15:30 - 09:15) / 5min


# ---------------------------------------------------------------------------
# Data quality types
# ---------------------------------------------------------------------------


class QualityFlag(str, Enum):
    ZERO_VOLUME = "zero_volume"
    OHLC_ERROR = "ohlc_error"
    NEGATIVE_PRICE = "negative_price"
    MISSING_INTERVAL = "missing_interval"
    DUPLICATE_TIMESTAMP = "duplicate_timestamp"
    OUT_OF_SESSION = "out_of_session"


@dataclass
class DataQualityIssue:
    """A single data quality finding for one candle."""
    flag: QualityFlag
    ticker: str
    timestamp_utc: datetime
    detail: str = ""

    def __str__(self) -> str:
        ts = self.timestamp_utc.strftime("%Y-%m-%d %H:%M UTC")
        return f"[{self.flag.value}] {self.ticker} @ {ts}: {self.detail}"


@dataclass
class DataQualityReport:
    """
    Aggregated quality summary produced by validate_candles().

    Attributes
    ----------
    ticker        : NSE ticker symbol
    start_utc     : first timestamp in input data
    end_utc       : last timestamp in input data
    total_candles : number of rows evaluated
    issues        : list of individual DataQualityIssue findings
    """
    ticker: str
    start_utc: Optional[datetime] = None
    end_utc: Optional[datetime] = None
    total_candles: int = 0
    issues: List[DataQualityIssue] = field(default_factory=list)

    # --- counts by flag ---
    @property
    def zero_volume_count(self) -> int:
        return sum(1 for i in self.issues if i.flag == QualityFlag.ZERO_VOLUME)

    @property
    def ohlc_error_count(self) -> int:
        return sum(1 for i in self.issues if i.flag == QualityFlag.OHLC_ERROR)

    @property
    def missing_count(self) -> int:
        return sum(1 for i in self.issues if i.flag == QualityFlag.MISSING_INTERVAL)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for i in self.issues if i.flag == QualityFlag.DUPLICATE_TIMESTAMP)

    @property
    def out_of_session_count(self) -> int:
        return sum(1 for i in self.issues if i.flag == QualityFlag.OUT_OF_SESSION)

    @property
    def is_clean(self) -> bool:
        """True if no issues detected (zero_volume warnings are non-fatal)."""
        fatal_flags = {
            QualityFlag.OHLC_ERROR,
            QualityFlag.NEGATIVE_PRICE,
            QualityFlag.DUPLICATE_TIMESTAMP,
            QualityFlag.OUT_OF_SESSION,
        }
        return not any(i.flag in fatal_flags for i in self.issues)

    def summary(self) -> str:
        return (
            f"DataQualityReport({self.ticker}: "
            f"{self.total_candles} candles, "
            f"{len(self.issues)} issues — "
            f"zero_vol={self.zero_volume_count}, "
            f"ohlc_err={self.ohlc_error_count}, "
            f"missing={self.missing_count}, "
            f"dupes={self.duplicate_count}, "
            f"out_of_session={self.out_of_session_count})"
        )


# ---------------------------------------------------------------------------
# Pure helper functions (no I/O, fully testable)
# ---------------------------------------------------------------------------


def normalize_to_utc(df: pd.DataFrame, ts_col: str = "timestamp") -> pd.DataFrame:
    """
    Convert a timestamp column from IST (Asia/Kolkata) to UTC.

    If the column is already tz-aware, it is converted to UTC.
    If tz-naive, it is assumed to be IST and localized before conversion.

    Returns a new DataFrame with the column replaced by UTC-aware datetimes.
    The column is renamed to 'timestamp_utc'.

    Args:
        df     : DataFrame with a timestamp column
        ts_col : name of the timestamp column (default "timestamp")

    Returns:
        New DataFrame; original is not mutated.
    """
    df = df.copy()
    col = pd.to_datetime(df[ts_col])

    if col.dt.tz is None:
        col = col.dt.tz_localize("Asia/Kolkata")

    col = col.dt.tz_convert("UTC")
    df["timestamp_utc"] = col
    if ts_col != "timestamp_utc":
        df = df.drop(columns=[ts_col])
    return df


def _nse_session_slots_utc(trading_date: date) -> List[datetime]:
    """
    Return the 75 expected UTC timestamps for a given NSE trading date.

    Args:
        trading_date: a date object (must be a trading day — caller's responsibility)

    Returns:
        List of 75 UTC datetime objects, one per 5-min bar
        (open time of each bar, in UTC).
    """
    # First bar opens at 09:15 IST
    slot_ist = datetime(
        trading_date.year, trading_date.month, trading_date.day,
        _NSE_OPEN_H, _NSE_OPEN_M, 0,
        tzinfo=IST,
    )
    slots = []
    for i in range(_SLOTS_PER_DAY):
        slots.append(slot_ist.astimezone(UTC).replace(tzinfo=UTC))
        slot_ist += timedelta(minutes=_INTERVAL_MINUTES)
    return slots


def detect_missing_intervals(
    df: pd.DataFrame,
    trading_dates: Sequence[date],
    ts_col: str = "timestamp_utc",
) -> List[datetime]:
    """
    Return UTC timestamps that are expected but absent from df.

    Uses NSE session schedule: 75 five-minute slots per trading day
    (09:15–15:25 IST open times, in UTC).

    Args:
        df             : DataFrame with a 'timestamp_utc' column (UTC-aware datetimes)
        trading_dates  : list/sequence of date objects to check (trading days only)
        ts_col         : name of the timestamp column

    Returns:
        Sorted list of missing UTC datetime objects.
    """
    present: set = set()
    if ts_col in df.columns and len(df) > 0:
        series = pd.to_datetime(df[ts_col])
        if series.dt.tz is None:
            series = series.dt.tz_localize("UTC")
        else:
            series = series.dt.tz_convert("UTC")
        # Normalize to UTC, strip sub-minute precision
        present = {
            dt.replace(second=0, microsecond=0)
            for dt in series
        }

    missing = []
    for d in trading_dates:
        for expected in _nse_session_slots_utc(d):
            normalized = expected.replace(second=0, microsecond=0)
            if normalized not in present:
                missing.append(expected)
    return sorted(missing)


def validate_candles(
    df: pd.DataFrame,
    ticker: str,
    ts_col: str = "timestamp_utc",
) -> DataQualityReport:
    """
    Validate a candle DataFrame and return a DataQualityReport.

    Checks performed (all per-candle):
      1. Duplicate timestamps
      2. Negative prices (open/high/low/close < 0)
      3. OHLC consistency: high >= max(open,close) AND low <= min(open,close)
      4. Zero volume
      5. Out-of-session candles (timestamp outside 09:15–15:25 IST)

    Args:
        df     : DataFrame with columns: timestamp_utc, open, high, low, close, volume
        ticker : ticker symbol for issue labelling
        ts_col : name of the timestamp column

    Returns:
        DataQualityReport (never raises; issues list may be empty)
    """
    report = DataQualityReport(ticker=ticker, total_candles=len(df))
    if df.empty:
        return report

    # Normalize timestamps to UTC-aware
    timestamps = pd.to_datetime(df[ts_col])
    if timestamps.dt.tz is None:
        timestamps = timestamps.dt.tz_localize("UTC")
    else:
        timestamps = timestamps.dt.tz_convert("UTC")

    report.start_utc = timestamps.min().to_pydatetime()
    report.end_utc = timestamps.max().to_pydatetime()

    # 1. Duplicate timestamps
    dupes = timestamps[timestamps.duplicated()]
    for ts in dupes:
        report.issues.append(DataQualityIssue(
            flag=QualityFlag.DUPLICATE_TIMESTAMP,
            ticker=ticker,
            timestamp_utc=ts.to_pydatetime(),
            detail="duplicate timestamp",
        ))

    # Vectorised checks on price columns
    opens = df["open"].astype(float)
    highs = df["high"].astype(float)
    lows = df["low"].astype(float)
    closes = df["close"].astype(float)
    volumes = df["volume"].astype(float)

    # 2. Negative prices
    neg_mask = (opens < 0) | (highs < 0) | (lows < 0) | (closes < 0)
    for idx in df.index[neg_mask]:
        report.issues.append(DataQualityIssue(
            flag=QualityFlag.NEGATIVE_PRICE,
            ticker=ticker,
            timestamp_utc=timestamps.iloc[df.index.get_loc(idx)].to_pydatetime(),
            detail=f"o={opens[idx]:.2f} h={highs[idx]:.2f} l={lows[idx]:.2f} c={closes[idx]:.2f}",
        ))

    # 3. OHLC consistency
    expected_high = opens.combine(closes, max)
    expected_low = opens.combine(closes, min)
    ohlc_err_mask = (highs < expected_high) | (lows > expected_low)
    for idx in df.index[ohlc_err_mask]:
        loc = df.index.get_loc(idx)
        report.issues.append(DataQualityIssue(
            flag=QualityFlag.OHLC_ERROR,
            ticker=ticker,
            timestamp_utc=timestamps.iloc[loc].to_pydatetime(),
            detail=(
                f"h={highs[idx]:.2f}<max(o,c)={expected_high[idx]:.2f} "
                f"or l={lows[idx]:.2f}>min(o,c)={expected_low[idx]:.2f}"
            ),
        ))

    # 4. Zero volume
    zero_vol_mask = volumes == 0
    for idx in df.index[zero_vol_mask]:
        loc = df.index.get_loc(idx)
        report.issues.append(DataQualityIssue(
            flag=QualityFlag.ZERO_VOLUME,
            ticker=ticker,
            timestamp_utc=timestamps.iloc[loc].to_pydatetime(),
            detail="volume=0",
        ))

    # 5. Out-of-session (09:15–15:25 IST)
    ts_ist = timestamps.dt.tz_convert("Asia/Kolkata")
    session_start = ts_ist.apply(
        lambda t: t.replace(hour=_NSE_OPEN_H, minute=_NSE_OPEN_M, second=0, microsecond=0)
    )
    session_end = ts_ist.apply(
        lambda t: t.replace(hour=_NSE_CLOSE_H - 0, minute=_NSE_CLOSE_M - _INTERVAL_MINUTES, second=0, microsecond=0)
    )
    out_mask = (ts_ist < session_start) | (ts_ist > session_end)
    for iloc, is_out in enumerate(out_mask):
        if is_out:
            report.issues.append(DataQualityIssue(
                flag=QualityFlag.OUT_OF_SESSION,
                ticker=ticker,
                timestamp_utc=timestamps.iloc[iloc].to_pydatetime(),
                detail=f"IST={ts_ist.iloc[iloc].strftime('%H:%M')} outside 09:15–15:25",
            ))

    return report


def apply_quality_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add boolean quality-flag columns to a candle DataFrame in-place equivalent.

    Columns added:
      - is_zero_volume   (bool)
      - has_ohlc_error   (bool)
      - is_interpolated  (bool, default False — set by caller after gap-fill)

    Args:
        df: DataFrame with open/high/low/close/volume columns

    Returns:
        New DataFrame with the flag columns added.
    """
    df = df.copy()
    opens = df["open"].astype(float)
    highs = df["high"].astype(float)
    lows = df["low"].astype(float)
    closes = df["close"].astype(float)
    volumes = df["volume"].astype(float)

    df["is_zero_volume"] = volumes == 0

    expected_high = opens.combine(closes, max)
    expected_low = opens.combine(closes, min)
    df["has_ohlc_error"] = (highs < expected_high) | (lows > expected_low)

    if "is_interpolated" not in df.columns:
        df["is_interpolated"] = False

    return df


# ---------------------------------------------------------------------------
# CandleStore  — async DB layer
# ---------------------------------------------------------------------------


class CandleStore:
    """
    Async read/write interface for the candles_5m table.

    All methods accept an AsyncSession from database.connection.
    No session lifecycle management here — caller owns the session.

    Example
    -------
        async with get_session() as session:
            store = CandleStore()
            await store.upsert(session, "RELIANCE", df)
            df_out = await store.fetch(session, "RELIANCE", date(2024,1,1), date(2024,1,31))
    """

    async def upsert(
        self,
        session,
        ticker: str,
        df: pd.DataFrame,
        source: str = "groww_api",
    ) -> Tuple[int, int]:
        """
        Upsert candles from df into candles_5m.

        Skips rows that already exist (ON CONFLICT DO NOTHING on
        the unique key (ticker, timestamp_utc)).

        Args:
            session : AsyncSession
            ticker  : NSE ticker
            df      : DataFrame with columns: timestamp_utc, open, high, low,
                      close, volume, and optionally vwap, is_zero_volume,
                      has_ohlc_error, is_interpolated
            source  : provenance label (default "groww_api")

        Returns:
            (inserted, skipped) counts
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from database.models_market import Candle5m

        if df.empty:
            return 0, 0

        df = apply_quality_flags(df)
        now_utc = datetime.now(UTC)

        rows = []
        for _, row in df.iterrows():
            ts = row["timestamp_utc"]
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)

            rows.append({
                "ticker": ticker,
                "timestamp_utc": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "vwap": float(row["vwap"]) if "vwap" in row and pd.notna(row["vwap"]) else None,
                "is_zero_volume": bool(row.get("is_zero_volume", False)),
                "has_ohlc_error": bool(row.get("has_ohlc_error", False)),
                "is_interpolated": bool(row.get("is_interpolated", False)),
                "source": source,
                "retrieved_at": now_utc,
            })

        stmt = pg_insert(Candle5m).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["ticker", "timestamp_utc"]
        )
        result = await session.execute(stmt)
        inserted = result.rowcount if result.rowcount >= 0 else len(rows)
        skipped = len(rows) - inserted
        await session.commit()
        return inserted, skipped

    async def fetch(
        self,
        session,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """
        Fetch candles for ticker between start_date and end_date (inclusive, UTC).

        Returns:
            DataFrame with columns: timestamp_utc, open, high, low, close,
            volume, vwap, is_zero_volume, has_ohlc_error, is_interpolated, source
            Sorted ascending by timestamp_utc.
        """
        from sqlalchemy import select, and_
        from database.models_market import Candle5m

        start_utc = datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC)
        end_utc = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=UTC)

        stmt = (
            select(Candle5m)
            .where(
                and_(
                    Candle5m.ticker == ticker,
                    Candle5m.timestamp_utc >= start_utc,
                    Candle5m.timestamp_utc <= end_utc,
                )
            )
            .order_by(Candle5m.timestamp_utc)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return pd.DataFrame(columns=[
                "timestamp_utc", "open", "high", "low", "close",
                "volume", "vwap", "is_zero_volume", "has_ohlc_error",
                "is_interpolated", "source",
            ])

        return pd.DataFrame([{
            "timestamp_utc": r.timestamp_utc,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "vwap": r.vwap,
            "is_zero_volume": r.is_zero_volume,
            "has_ohlc_error": r.has_ohlc_error,
            "is_interpolated": r.is_interpolated,
            "source": r.source,
        } for r in rows])

    async def ticker_date_coverage(
        self,
        session,
        ticker: str,
    ) -> Dict[date, int]:
        """
        Return a dict of {trading_date: candle_count} for all stored dates.

        Useful for identifying gaps before downloading.
        """
        from sqlalchemy import select, func, cast
        from sqlalchemy.types import Date
        from database.models_market import Candle5m

        # Cast UTC timestamp to IST date for grouping
        # PostgreSQL: (timestamp_utc AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date
        stmt = (
            select(
                func.cast(
                    func.timezone("Asia/Kolkata", func.timezone("UTC", Candle5m.timestamp_utc)),
                    Date,
                ).label("ist_date"),
                func.count().label("cnt"),
            )
            .where(Candle5m.ticker == ticker)
            .group_by("ist_date")
            .order_by("ist_date")
        )
        result = await session.execute(stmt)
        return {row.ist_date: row.cnt for row in result}


# ---------------------------------------------------------------------------
# CandleDownloader  — orchestration
# ---------------------------------------------------------------------------


class CandleDownloader:
    """
    Orchestrates downloading Nifty 100 candle data from the Groww API.

    Workflow per ticker:
      1. Determine date range to download
      2. Chunk into ≤30-day windows (Groww API limit)
      3. For each chunk: fetch → normalize_to_utc → validate → upsert
      4. Update DataDownloadJob status/progress in DB
      5. Return summary dict

    Example
    -------
        from app.market.candles import CandleDownloader
        from app.market.instruments import get_registry

        downloader = CandleDownloader()
        summary = await downloader.download_ticker(
            session=session,
            ticker="RELIANCE",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
        )
        print(summary)
    """

    def __init__(self, interval_minutes: int = 5) -> None:
        self._interval = interval_minutes
        self._store = CandleStore()

    async def download_ticker(
        self,
        session,
        ticker: str,
        start_date: date,
        end_date: date,
        groww_symbol: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Download all candles for one ticker over start_date..end_date.

        Args:
            session      : AsyncSession
            ticker       : NSE ticker
            start_date   : first date to download (inclusive)
            end_date     : last date to download (inclusive)
            groww_symbol : override Groww API symbol (default: "NSE-{ticker}")
            job_id       : DataDownloadJob UUID to update (optional)

        Returns:
            Summary dict with keys: ticker, start_date, end_date,
            chunks_attempted, candles_downloaded, candles_skipped,
            quality_issues, errors.
        """
        from app.market.historical_data import fetch_candles_chunked, CandleInterval

        sym = groww_symbol or f"NSE-{ticker}"
        summary: Dict[str, Any] = {
            "ticker": ticker,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "chunks_attempted": 0,
            "candles_downloaded": 0,
            "candles_skipped": 0,
            "quality_issues": 0,
            "errors": [],
        }

        logger.info("CandleDownloader: %s %s → %s", ticker, start_date, end_date)

        try:
            df_all = await fetch_candles_chunked(
                symbol=sym,
                start_date=start_date,
                end_date=end_date,
                interval=CandleInterval.MINUTE_5,
            )
        except Exception as exc:
            msg = f"fetch failed: {exc}"
            logger.error("CandleDownloader %s: %s", ticker, msg)
            summary["errors"].append(msg)
            await self._update_job(session, job_id, "failed", summary)
            return summary

        summary["chunks_attempted"] = 1  # fetch_candles_chunked handles internally

        if df_all.empty:
            logger.warning("CandleDownloader %s: no data returned", ticker)
            await self._update_job(session, job_id, "completed", summary)
            return summary

        # Normalize timestamps to UTC
        df_all = normalize_to_utc(df_all, ts_col="timestamp")

        # Validate
        report = validate_candles(df_all, ticker=ticker)
        summary["quality_issues"] = len(report.issues)
        if not report.is_clean:
            logger.warning(
                "CandleDownloader %s: %d quality issues detected",
                ticker, len(report.issues),
            )
            for issue in report.issues[:5]:  # log first 5
                logger.debug("  %s", issue)

        # Upsert
        try:
            inserted, skipped = await self._store.upsert(session, ticker, df_all)
            summary["candles_downloaded"] = inserted
            summary["candles_skipped"] = skipped
        except Exception as exc:
            msg = f"upsert failed: {exc}"
            logger.error("CandleDownloader %s: %s", ticker, msg)
            summary["errors"].append(msg)
            await self._update_job(session, job_id, "failed", summary)
            return summary

        await self._update_job(session, job_id, "completed", summary)
        logger.info(
            "CandleDownloader %s: inserted=%d skipped=%d issues=%d",
            ticker, inserted, skipped, len(report.issues),
        )
        return summary

    async def download_index(
        self,
        session,
        index_name: str = "NIFTY100",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        tickers: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Download candles for all tickers in an index.

        Args:
            session    : AsyncSession
            index_name : e.g. "NIFTY100"
            start_date : defaults to 365 days ago
            end_date   : defaults to today
            tickers    : override ticker list (useful for partial re-runs)

        Returns:
            List of per-ticker summary dicts.
        """
        from app.market.instruments import get_registry

        today = date.today()
        start = start_date or (today - timedelta(days=365))
        end = end_date or today

        registry = get_registry()
        ticker_list = tickers or registry.members_as_of(str(end))

        results = []
        for ticker in ticker_list:
            inst = registry.get(ticker)
            groww_sym = inst.groww_symbol if inst else f"NSE-{ticker}"
            summary = await self.download_ticker(
                session=session,
                ticker=ticker,
                start_date=start,
                end_date=end,
                groww_symbol=groww_sym,
            )
            results.append(summary)

        return results

    async def _update_job(
        self,
        session,
        job_id: Optional[str],
        status: str,
        summary: Dict[str, Any],
    ) -> None:
        """Update DataDownloadJob row if job_id provided."""
        if job_id is None:
            return
        try:
            from sqlalchemy import update
            from database.models_market import DataDownloadJob
            stmt = (
                update(DataDownloadJob)
                .where(DataDownloadJob.id == job_id)
                .values(
                    status=status,
                    candles_downloaded=summary.get("candles_downloaded", 0),
                    candles_skipped_duplicates=summary.get("candles_skipped", 0),
                )
            )
            await session.execute(stmt)
            await session.commit()
        except Exception as exc:
            logger.warning("CandleDownloader: failed to update job %s: %s", job_id, exc)