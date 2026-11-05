"""
Live market data — REST polling and WebSocket/NATS streaming.

Two modes
---------
1. **REST polling** (via GrowwClient)
   - ``get_ltp_rest``    — LTP for one or more symbols
   - ``get_ohlc_rest``   — OHLC snapshot for one or more symbols
   - ``get_quote_rest``  — Full quote (LTP + bid/ask depth) for one symbol

2. **WebSocket streaming** (via GrowwFeed / NATS)
   - ``LiveDataFeed``  — high-level manager for LTP + depth subscriptions
   - Callback-driven: ``on_ltp_update(symbol, ltp)``
   - Thread-safe: GrowwFeed runs its NATS consumer on a background thread

Which to use
------------
- Backtesting:    neither — use historical_data.fetch_candles_chunked
- Paper trading:  REST polling at candle close time is sufficient
- Live (blocked): Feed streaming would be needed; order placement is blocked

Instrument dict format required by GrowwFeed
--------------------------------------------
    {"exchange": "NSE", "trading_symbol": "RELIANCE", "segment": "CASH"}
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# REST helpers (stateless)
# ---------------------------------------------------------------------------

def get_ltp_rest(
    client,
    symbols: List[str],
    exchange: str = "NSE",
    segment: str = "CASH",
) -> Dict[str, float]:
    """
    Fetch last traded price for one or more symbols via REST (polling).

    Parameters
    ----------
    client : GrowwClient
        Authenticated GrowwClient instance.
    symbols : list of str
        NSE trading symbols, e.g. ``["RELIANCE", "INFY", "TCS"]``.
    exchange : str
        Exchange code (default ``"NSE"``).
    segment : str
        Market segment (default ``"CASH"``).

    Returns
    -------
    dict
        ``{symbol: ltp_float}`` mapping.
        Symbols missing from response are silently omitted.

    Notes
    -----
    Uses ``GrowwAPI.get_ltp(exchange_trading_symbols, segment)``.
    exchange_symbols format: ``("NSE_RELIANCE", "NSE_INFY")``.
    """
    raw = client.get_ltp(symbols=symbols, exchange=exchange, segment=segment)
    result: Dict[str, float] = {}
    for key, data in raw.items():
        # key format may be "NSE_RELIANCE" or similar
        sym = key.split("_", 1)[-1] if "_" in key else key
        ltp = data.get("ltp") if isinstance(data, dict) else data
        if ltp is not None:
            try:
                result[sym] = float(ltp)
            except (ValueError, TypeError):
                logger.warning("Could not parse LTP for %s: %r", sym, ltp)
    return result


def get_ohlc_rest(
    client,
    symbols: List[str],
    exchange: str = "NSE",
    segment: str = "CASH",
) -> Dict[str, dict]:
    """
    OHLC snapshot for one or more symbols via REST.

    Returns
    -------
    dict
        ``{symbol: {"open": float, "high": float, "low": float, "close": float}}``
    """
    raw = client.get_ohlc(symbols=symbols, exchange=exchange, segment=segment)
    result: Dict[str, dict] = {}
    for key, data in raw.items():
        sym = key.split("_", 1)[-1] if "_" in key else key
        if isinstance(data, dict):
            result[sym] = {
                "open":  float(data.get("open",  0)),
                "high":  float(data.get("high",  0)),
                "low":   float(data.get("low",   0)),
                "close": float(data.get("close", 0)),
            }
    return result


def get_quote_rest(
    client,
    trading_symbol: str,
    exchange: str = "NSE",
    segment: str = "CASH",
) -> dict:
    """
    Full quote (LTP + bid/ask depth) for a single instrument via REST.

    Returns the raw response dict from the Groww API.
    Typical keys: ltp, open, high, low, close, volume, buy_quantity,
                  sell_quantity, depth (bid/ask levels).
    """
    return client.get_quote(
        trading_symbol=trading_symbol,
        exchange=exchange,
        segment=segment,
    )


# ---------------------------------------------------------------------------
# WebSocket/NATS streaming feed manager
# ---------------------------------------------------------------------------

def _make_instrument(
    trading_symbol: str,
    exchange: str = "NSE",
    segment: str = "CASH",
) -> dict:
    return {"exchange": exchange, "trading_symbol": trading_symbol, "segment": segment}


class LiveDataFeed:
    """
    High-level manager for real-time market data via GrowwFeed (NATS).

    Usage
    -----
    ::

        feed = LiveDataFeed(client)
        feed.subscribe_ltp(
            symbols=["RELIANCE", "INFY"],
            on_ltp=lambda sym, price: print(sym, price),
        )
        # ... run your loop ...
        snapshot = feed.get_ltp_snapshot()
        feed.unsubscribe_all()

    Thread safety
    -------------
    GrowwFeed runs its NATS consumer on a background daemon thread started
    internally by the SDK. ``on_ltp`` callbacks are invoked from that thread;
    keep them short and thread-safe (avoid blocking I/O).

    Notes
    -----
    - ``GrowwFeed(groww_api)`` requires a valid ``GrowwAPI`` instance (not just token).
    - Subscription is confirmed when the first callback fires or after the
      NATS handshake completes.
    - ``get_ltp_snapshot()`` returns the most recently received value for each
      subscribed instrument — it does NOT block waiting for the next tick.
    """

    def __init__(self, client) -> None:
        """
        Parameters
        ----------
        client : GrowwClient
            Authenticated GrowwClient instance.
        """
        self._client = client
        self._subscribed_ltp: List[dict] = []
        self._subscribed_depth: List[dict] = []
        self._lock = threading.Lock()
        self._ltp_cache: Dict[str, float] = {}

    # ------------------------------------------------------------------
    def subscribe_ltp(
        self,
        symbols: List[str],
        exchange: str = "NSE",
        segment: str = "CASH",
        on_ltp: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        """
        Subscribe to real-time LTP updates for a list of symbols.

        Parameters
        ----------
        symbols : list of str
            Trading symbols, e.g. ``["RELIANCE", "INFY"]``.
        exchange : str
            Exchange (default ``"NSE"``).
        segment : str
            Segment (default ``"CASH"``).
        on_ltp : callable, optional
            Called as ``on_ltp(trading_symbol, ltp_float)`` whenever LTP changes.
            Runs on the GrowwFeed background thread.

        Notes
        -----
        Calling subscribe_ltp multiple times adds to the existing subscriptions.
        Use unsubscribe_ltp or unsubscribe_all to clean up.
        """
        instruments = [_make_instrument(sym, exchange, segment) for sym in symbols]

        def _on_data_received():
            """Internal callback — extracts LTP and calls user callback."""
            snapshot = self._client.get_ltp_snapshot()
            with self._lock:
                for key, data in snapshot.items():
                    sym = key.split("_", 1)[-1] if "_" in key else key
                    ltp = None
                    if isinstance(data, dict):
                        ltp = data.get("ltp") or data.get("last_traded_price")
                    elif isinstance(data, (int, float)):
                        ltp = data
                    if ltp is not None:
                        self._ltp_cache[sym] = float(ltp)
                        if on_ltp:
                            try:
                                on_ltp(sym, float(ltp))
                            except Exception as exc:
                                logger.error("on_ltp callback raised: %s", exc)

        self._client.subscribe_ltp(instruments=instruments, on_data_received=_on_data_received)

        with self._lock:
            self._subscribed_ltp.extend(instruments)

        logger.info("Subscribed LTP feed for: %s", symbols)

    # ------------------------------------------------------------------
    def subscribe_market_depth(
        self,
        symbols: List[str],
        exchange: str = "NSE",
        segment: str = "CASH",
        on_depth: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        """
        Subscribe to real-time bid/ask market depth for a list of symbols.

        Parameters
        ----------
        on_depth : callable, optional
            Called as ``on_depth(trading_symbol, depth_dict)`` on each update.
        """
        instruments = [_make_instrument(sym, exchange, segment) for sym in symbols]

        def _on_depth_received():
            depth_snapshot = self._client.get_market_depth_snapshot()
            for key, data in depth_snapshot.items():
                sym = key.split("_", 1)[-1] if "_" in key else key
                if on_depth and isinstance(data, dict):
                    try:
                        on_depth(sym, data)
                    except Exception as exc:
                        logger.error("on_depth callback raised: %s", exc)

        self._client.subscribe_market_depth(
            instruments=instruments, on_data_received=_on_depth_received
        )

        with self._lock:
            self._subscribed_depth.extend(instruments)

        logger.info("Subscribed market depth feed for: %s", symbols)

    # ------------------------------------------------------------------
    def get_ltp_snapshot(self) -> Dict[str, float]:
        """
        Return the most recently received LTP for all subscribed symbols.

        Returns the internal cache (updated by callbacks). If no data has
        arrived yet, returns an empty dict.
        """
        with self._lock:
            return dict(self._ltp_cache)

    # ------------------------------------------------------------------
    def unsubscribe_ltp(
        self,
        symbols: Optional[List[str]] = None,
        exchange: str = "NSE",
        segment: str = "CASH",
    ) -> None:
        """
        Unsubscribe from LTP feed for specific symbols (or all if symbols=None).
        """
        with self._lock:
            if symbols is None:
                instruments = list(self._subscribed_ltp)
                self._subscribed_ltp.clear()
            else:
                instruments = [_make_instrument(sym, exchange, segment) for sym in symbols]
                self._subscribed_ltp = [
                    i for i in self._subscribed_ltp
                    if i.get("trading_symbol") not in symbols
                ]

        if instruments:
            self._client.unsubscribe_ltp(instruments)
            logger.info("Unsubscribed LTP feed for %d instruments.", len(instruments))

    # ------------------------------------------------------------------
    def unsubscribe_all(self) -> None:
        """Unsubscribe from all LTP subscriptions."""
        self.unsubscribe_ltp(symbols=None)
        logger.info("All LTP feed subscriptions cancelled.")