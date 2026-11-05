"""NSE trading hours utilities."""
from __future__ import annotations

from datetime import datetime, time

import pytz

_IST = pytz.timezone("Asia/Kolkata")
_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)


def _now_ist() -> datetime:
    return datetime.now(_IST)


def is_market_open(dt: datetime | None = None) -> bool:
    """
    Return True if NSE is currently open (09:15–15:30 IST, Mon–Fri).

    Args:
        dt: Datetime to check (defaults to now).
    """
    dt = dt or _now_ist()
    if not dt.tzinfo:
        dt = _IST.localize(dt)
    else:
        dt = dt.astimezone(_IST)

    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = dt.time()
    return _MARKET_OPEN <= t <= _MARKET_CLOSE


def is_trading_allowed(
    dt: datetime | None = None,
    avoid_first_minutes: int = 15,
    avoid_last_minutes: int = 15,
) -> bool:
    """
    Return True if it is safe to place orders (avoids first/last N minutes).

    Args:
        dt: Datetime to check (defaults to now).
        avoid_first_minutes: Skip first N minutes after open.
        avoid_last_minutes: Skip last N minutes before close.
    """
    dt = dt or _now_ist()
    if not dt.tzinfo:
        dt = _IST.localize(dt)
    else:
        dt = dt.astimezone(_IST)

    if not is_market_open(dt):
        return False

    t = dt.time()
    # e.g. avoid first 15 min → allow from 09:30
    open_h, open_m = divmod(_MARKET_OPEN.hour * 60 + _MARKET_OPEN.minute + avoid_first_minutes, 60)
    close_h, close_m = divmod(_MARKET_CLOSE.hour * 60 + _MARKET_CLOSE.minute - avoid_last_minutes, 60)

    allowed_start = time(open_h, open_m)
    allowed_end = time(close_h, close_m)
    return allowed_start <= t <= allowed_end