"""
Historical candle data retrieval for the Groww Trading API.

Key constraint (from official docs)
------------------------------------
``get_historical_candles`` (SDK v2) accepts a maximum of **30 calendar days**
per request for intraday intervals (1min – 4hour).

This module provides ``fetch_candles_chunked`` which splits any date range
into ≤30-day chunks, makes individual requests, then concatenates results
into a single pandas DataFrame.

Candle interval used by this project: ``GrowwAPI.CANDLE_INTERVAL_MIN_5`` → ``"5minute"``

Time format required by the API: ``"yyyy-MM-dd HH:mm:ss"``
  NSE session: 09:15:00 – 15:30:00 IST

Rate-limit safety: 1-second sleep between chunk requests.

Usage
-----
    from app.market.historical_data import fetch_candles_chunked, CandleInterval
    from app.broker.groww_client import GrowwClient

    client = GrowwClient(access_token="<token>")
    df = fetch_candles_chunked(
        client=client,
        groww_symbol="NSE-RELIANCE",
        start_date="2023-01-01",
        end_date="2023-06-30",
        interval=CandleInterval.MIN_5,
    )
    print(df.head())
    # Columns: timestamp, open, high, low, close, volume
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_CHUNK_DAYS = 30          # API hard limit per request
_INTER_REQUEST_SLEEP = 1.0    # seconds between chunks (rate-limit safety)

# NSE intraday session boundaries
_SESSION_START = "09:15:00"
_SESSION_END   = "15:30:00"


class CandleInterval:
    """
    Candle interval constants matching ``GrowwAPI.CANDLE_INTERVAL_*``.

    Use ``CandleInterval.MIN_5`` for 5-minute intraday data.
    """
    MIN_1   = "1minute"
    MIN_2   = "2minute"
    MIN_3   = "3minute"
    MIN_5   = "5minute"
    MIN_10  = "10minute"
    MIN_15  = "15minute"
    MIN_30  = "30minute"
    HOUR_1  = "1hour"
    HOUR_4  = "4hour"
    DAY     = "1day"
    WEEK    = "1week"
    MONTH   = "1month"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fmt(dt: datetime) -> str:
    """Format a datetime to the string expected by the Groww API."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _date_chunks(
    start: datetime,
    end: datetime,
    max_days: int = _MAX_CHUNK_DAYS,
):
    """
    Generate (chunk_start, chunk_end) pairs that cover [start, end]
    in steps of ``max_days``.
    """
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=max_days - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(seconds=1)


def _response_to_dataframe(response: dict) -> pd.DataFrame:
    """
    Convert the ``get_historical_candles`` response payload to a DataFrame.

    The v2 API returns a dict with a ``"candles"`` key containing a list of
    lists: ``[timestamp_ms, open, high, low, close, volume, oi]``
    (OI may be absent for equity cash).

    Returns a DataFrame with columns:
        timestamp (datetime, IST), open, high, low, close, volume
    """
    candles = response.get("candles", [])
    if not candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    rows = []
    for candle in candles:
        # SDK v2 format: [epoch_ms, open, high, low, close, volume, (oi)]
        if len(candle) < 6:
            logger.warning("Skipping malformed candle: %s", candle)
            continue
        ts_ms, open_, high, low, close, volume = candle[:6]
        rows.append({
            "timestamp": pd.Timestamp(ts_ms, unit="ms", tz="Asia/Kolkata"),
            "open":   float(open_),
            "high":   float(high),
            "low":    float(low),
            "close":  float(close),
            "volume": int(volume),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_candles_chunked(
    client,                          # GrowwClient instance
    groww_symbol: str,
    start_date: str,
    end_date: str,
    interval: str = CandleInterval.MIN_5,
    exchange: str = "NSE",
    segment: str = "CASH",
    sleep_between_chunks: float = _INTER_REQUEST_SLEEP,
) -> pd.DataFrame:
    """
    Fetch historical candles for ``groww_symbol`` over an arbitrary date range,
    automatically splitting into ≤30-day chunks.

    Parameters
    ----------
    client : GrowwClient
        Authenticated GrowwClient instance.
    groww_symbol : str
        Groww symbol, e.g. ``"NSE-RELIANCE"``.
    start_date : str
        Start date in ``"YYYY-MM-DD"`` format (inclusive).
    end_date : str
        End date in ``"YYYY-MM-DD"`` format (inclusive).
    interval : str
        Candle interval from ``CandleInterval.*``. Default: ``"5minute"``.
    exchange : str
        Exchange code (default ``"NSE"``).
    segment : str
        Market segment (default ``"CASH"``).
    sleep_between_chunks : float
        Seconds to sleep between requests (default 1.0).

    Returns
    -------
    pd.DataFrame
        Columns: ``timestamp``, ``open``, ``high``, ``low``, ``close``, ``volume``
        ``timestamp`` is timezone-aware (Asia/Kolkata).
        Returns empty DataFrame if no data is available.

    Raises
    ------
    ValueError
        If start_date > end_date, or if dates cannot be parsed.
    RuntimeError
        If the GrowwAPI returns an error on any chunk.

    Notes
    -----
    - Maximum 30 calendar days per API request.
    - Only trading days are returned (weekends / NSE holidays have no candles).
    - Weekend days are still counted toward the 30-day chunk window.
    - For 5-minute candles, NSE session = 09:15 to 15:30 IST.
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
        hour=9, minute=15, second=0
    )
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
        hour=15, minute=30, second=0
    )

    if start_dt > end_dt:
        raise ValueError(f"start_date {start_date!r} must be ≤ end_date {end_date!r}.")

    # Normalise to midnight boundaries for chunking so intra-day times
    # (09:15 start, 15:30 end) don't create a spurious extra chunk.
    # For example: Jan 2 → Mar 1 (58 days) → 2 chunks, not 3.
    _chunk_start_norm = start_dt.replace(hour=0, minute=0, second=0)
    _chunk_end_norm   = end_dt.replace(hour=0, minute=0, second=0)
    # Same-date range (start and end on the same calendar day): _date_chunks
    # uses strict `<`, so equal boundaries yield 0 chunks. Add 1 second to
    # keep the loop alive for a single-chunk pass.
    if _chunk_end_norm <= _chunk_start_norm:
        _chunk_end_norm = _chunk_start_norm + timedelta(seconds=1)

    chunks = list(_date_chunks(_chunk_start_norm, _chunk_end_norm))
    logger.info(
        "Fetching %s candles for %s from %s to %s (%d chunk(s)).",
        interval, groww_symbol, start_date, end_date, len(chunks),
    )

    all_frames: list[pd.DataFrame] = []

    for idx, (chunk_start, chunk_end) in enumerate(chunks, start=1):
        # Re-apply NSE session times, clamped to the original start/end bounds.
        actual_start = max(
            chunk_start.replace(hour=9, minute=15, second=0), start_dt
        )
        actual_end = min(
            chunk_end.replace(hour=15, minute=30, second=0), end_dt
        )
        start_str = _fmt(actual_start)
        end_str   = _fmt(actual_end)
        logger.debug(
            "Chunk %d/%d: %s → %s", idx, len(chunks), start_str, end_str
        )

        try:
            response = client.api.get_historical_candles(
                exchange=exchange,
                segment=segment,
                groww_symbol=groww_symbol,
                start_time=start_str,
                end_time=end_str,
                candle_interval=interval,
                timeout=30,
            )
        except Exception as exc:
            logger.error(
                "Error fetching chunk %d/%d (%s → %s): %s",
                idx, len(chunks), start_str, end_str, exc,
            )
            raise RuntimeError(
                f"Failed to fetch candles for {groww_symbol} "
                f"({start_str} → {end_str}): {exc}"
            ) from exc

        frame = _response_to_dataframe(response)
        if not frame.empty:
            all_frames.append(frame)
            logger.debug("Chunk %d: received %d candles.", idx, len(frame))
        else:
            logger.debug("Chunk %d: no candles (holiday/weekend range?).", idx)

        if idx < len(chunks):
            time.sleep(sleep_between_chunks)

    if not all_frames:
        logger.warning("No candles returned for %s (%s → %s).", groww_symbol, start_date, end_date)
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

    combined = pd.concat(all_frames, ignore_index=True)
    combined.drop_duplicates(subset=["timestamp"], inplace=True)
    combined.sort_values("timestamp", inplace=True)
    combined.reset_index(drop=True, inplace=True)

    logger.info(
        "Fetched %d total candles for %s (%s → %s).",
        len(combined), groww_symbol, start_date, end_date,
    )
    return combined


def fetch_candles_single(
    client,
    groww_symbol: str,
    start_time: str,
    end_time: str,
    interval: str = CandleInterval.MIN_5,
    exchange: str = "NSE",
    segment: str = "CASH",
) -> pd.DataFrame:
    """
    Fetch candles for a single window (must be ≤30 days).

    Parameters
    ----------
    start_time : str
        ``"YYYY-MM-DD HH:MM:SS"`` format.
    end_time : str
        ``"YYYY-MM-DD HH:MM:SS"`` format.

    Raises
    ------
    ValueError
        If the requested window exceeds 30 days.
    """
    start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end_dt   = datetime.strptime(end_time,   "%Y-%m-%d %H:%M:%S")
    if (end_dt - start_dt).days > _MAX_CHUNK_DAYS:
        raise ValueError(
            f"Requested window is {(end_dt - start_dt).days} days — "
            f"exceeds the API limit of {_MAX_CHUNK_DAYS} days per request. "
            "Use fetch_candles_chunked() instead."
        )

    response = client.api.get_historical_candles(
        exchange=exchange,
        segment=segment,
        groww_symbol=groww_symbol,
        start_time=start_time,
        end_time=end_time,
        candle_interval=interval,
        timeout=30,
    )
    return _response_to_dataframe(response)


# ---------------------------------------------------------------------------
# UTC normalization and gap detection (re-exported from candles module)
# Defined here as thin wrappers so historical_data remains a one-stop import.
# ---------------------------------------------------------------------------

_IST = ZoneInfo("Asia/Kolkata")
_UTC = timezone.utc

_NSE_OPEN_H, _NSE_OPEN_M = 9, 15
_SLOTS_PER_DAY = 75
_INTERVAL_MINUTES = 5


def normalize_to_utc(df: pd.DataFrame, ts_col: str = "timestamp") -> pd.DataFrame:
    """
    Convert timestamp column from IST (Asia/Kolkata) to UTC.

    If tz-naive, assumes IST. Renames column to 'timestamp_utc'.
    Returns a new DataFrame (original not mutated).
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


def detect_gaps(
    df: pd.DataFrame,
    trading_dates: Sequence,
    ts_col: str = "timestamp_utc",
    interval_minutes: int = _INTERVAL_MINUTES,
) -> List[datetime]:
    """
    Return UTC timestamps that are expected (per NSE session schedule)
    but absent from df.

    Args:
        df             : DataFrame with timestamp_utc column (UTC-aware)
        trading_dates  : list of datetime.date objects (trading days only)
        ts_col         : column name for timestamps
        interval_minutes: bar width in minutes (default 5)

    Returns:
        Sorted list of missing UTC datetime objects.
    """
    from app.market.candles import detect_missing_intervals
    return detect_missing_intervals(df, trading_dates, ts_col=ts_col)