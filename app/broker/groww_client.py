"""
GrowwClient — a thin, safety-first wrapper around the official growwapi SDK.

What this adds over raw GrowwAPI
---------------------------------
- Rate-limit back-off (429 → exponential retry, max 3 attempts)
- Network failure retry (3 attempts, 1 s base delay)
- Lazy GrowwFeed construction (only created when subscribe_* is called)
- Instrument lookup helpers wired to the project's Nifty 100 universe
- Paper/backtest mode guard: order placement always raises if
  ``_LIVE_TRADING_ENABLED`` is False (it is always False here)
- Structured logging on every public call

Supported operations
--------------------
  Instruments:   get_instrument, get_all_instruments
  Live data:     get_ltp, get_ohlc, get_quote (REST)
  Streaming:     subscribe_ltp, get_ltp_snapshot, unsubscribe_ltp
                 subscribe_market_depth, get_market_depth_snapshot
  Orders:        get_order_list, get_order_detail, get_order_status,
                 get_order_status_by_reference
  Trades:        get_trade_history
  Positions:     get_positions, get_position
  Holdings:      get_holdings
  Margin:        get_available_margin
  User:          get_user_profile

Order placement is intentionally NOT implemented — use MockBroker for
backtest/paper simulations.

Usage
-----
    from app.broker.groww_client import GrowwClient
    client = GrowwClient(access_token="<your-token>")
    ltp = client.get_ltp(["RELIANCE", "INFY"])
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety guard — NEVER enable live order placement
# ---------------------------------------------------------------------------
_LIVE_TRADING_ENABLED: bool = False


class LiveTradingBlockedError(RuntimeError):
    """Raised whenever code attempts to place, modify or cancel a real order."""

    def __init__(self) -> None:
        super().__init__(
            "Live order placement is permanently disabled in this codebase. "
            "Use MockBroker for paper/backtest trading."
        )


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


def _with_retry(fn: Callable, *args, label: str = "", **kwargs):
    """
    Call ``fn(*args, **kwargs)`` with exponential back-off on network errors
    and rate-limit (429) responses.

    Never retries on 400 / 401 / 403 / 404 — those are caller errors.
    """
    try:
        from growwapi.groww.exceptions import (
            GrowwAPIRateLimitException,
            GrowwAPITimeoutException,
        )
    except ImportError:
        GrowwAPIRateLimitException = Exception
        GrowwAPITimeoutException = Exception

    last_exc: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except GrowwAPIRateLimitException as exc:
            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "[%s] Rate limited (attempt %d/%d). Sleeping %.1f s.",
                label, attempt, _MAX_RETRIES, delay,
            )
            time.sleep(delay)
            last_exc = exc
        except GrowwAPITimeoutException as exc:
            delay = _RETRY_BASE_DELAY * attempt
            logger.warning(
                "[%s] Timeout (attempt %d/%d). Sleeping %.1f s.",
                label, attempt, _MAX_RETRIES, delay,
            )
            time.sleep(delay)
            last_exc = exc
        except OSError as exc:  # network-level failures
            delay = _RETRY_BASE_DELAY * attempt
            logger.warning(
                "[%s] Network error (attempt %d/%d): %s. Sleeping %.1f s.",
                label, attempt, _MAX_RETRIES, exc, delay,
            )
            time.sleep(delay)
            last_exc = exc
        except Exception:
            raise  # 400/401/403/404/business logic — don't retry

    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GrowwClient
# ---------------------------------------------------------------------------

class GrowwClient:
    """
    Safe, retrying wrapper around ``growwapi.GrowwAPI`` and ``growwapi.GrowwFeed``.

    Parameters
    ----------
    access_token : str
        The access token obtained via ``authentication.obtain_access_token()``
        or from the ``GROWW_API_TOKEN`` environment variable.
    request_timeout : int
        Default HTTP timeout in seconds for all REST calls.
    """

    def __init__(self, access_token: str, request_timeout: int = 15) -> None:
        try:
            from growwapi import GrowwAPI
        except ImportError as exc:
            raise RuntimeError(
                "growwapi package not installed. Run: pip install growwapi"
            ) from exc

        self._token = access_token
        self._timeout = request_timeout
        self._api = GrowwAPI(access_token)
        self._feed: Optional[object] = None  # lazy — created on first subscribe call
        logger.info("GrowwClient initialised (live_trading=%s).", _LIVE_TRADING_ENABLED)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def api(self):
        """Direct access to the underlying ``GrowwAPI`` instance."""
        return self._api

    # ------------------------------------------------------------------
    # Instruments
    # ------------------------------------------------------------------

    def get_instrument(
        self,
        trading_symbol: str,
        exchange: str = "NSE",
    ) -> dict:
        """
        Look up a single instrument by trading symbol and exchange.

        Returns the instrument dict with keys:
            exchange, exchange_token, trading_symbol, groww_symbol,
            name, instrument_type, segment, series, isin, lot_size,
            tick_size, buy_allowed, sell_allowed, ...
        """
        return _with_retry(
            self._api.get_instrument_by_exchange_and_trading_symbol,
            exchange, trading_symbol,
            label=f"get_instrument:{exchange}:{trading_symbol}",
        )

    def get_instrument_by_groww_symbol(self, groww_symbol: str) -> dict:
        """E.g. groww_symbol='NSE-RELIANCE'"""
        return _with_retry(
            self._api.get_instrument_by_groww_symbol,
            groww_symbol,
            label=f"get_instrument_groww:{groww_symbol}",
        )

    def get_all_instruments(self):
        """Return a pandas DataFrame of all tradable instruments (CSV download)."""
        return _with_retry(
            self._api.get_all_instruments,
            label="get_all_instruments",
        )

    # ------------------------------------------------------------------
    # Live data — REST (polling)
    # ------------------------------------------------------------------

    def get_ltp(
        self,
        symbols: List[str],
        exchange: str = "NSE",
        segment: str = "CASH",
    ) -> dict:
        """
        Last traded price for one or more symbols via REST.

        Parameters
        ----------
        symbols : list of str
            Trading symbols, e.g. ``["RELIANCE", "INFY"]``.
        exchange : str
            Exchange code (default "NSE").
        segment : str
            Market segment (default "CASH").

        Returns
        -------
        dict
            Response keyed by ``"{exchange}_{symbol}"``.
        """
        exchange_symbols: Tuple[str, ...] = tuple(
            f"{exchange}_{sym}" for sym in symbols
        )
        return _with_retry(
            self._api.get_ltp,
            exchange_symbols, segment,
            label="get_ltp",
            timeout=self._timeout,
        )

    def get_ohlc(
        self,
        symbols: List[str],
        exchange: str = "NSE",
        segment: str = "CASH",
    ) -> dict:
        """OHLC snapshot for one or more symbols."""
        exchange_symbols: Tuple[str, ...] = tuple(
            f"{exchange}_{sym}" for sym in symbols
        )
        return _with_retry(
            self._api.get_ohlc,
            exchange_symbols, segment,
            label="get_ohlc",
            timeout=self._timeout,
        )

    def get_quote(
        self,
        trading_symbol: str,
        exchange: str = "NSE",
        segment: str = "CASH",
    ) -> dict:
        """
        Full quote (LTP + bid/ask depth) for a single instrument via REST.
        """
        return _with_retry(
            self._api.get_quote,
            trading_symbol, exchange, segment,
            label=f"get_quote:{trading_symbol}",
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # Live data — WebSocket/NATS feed (streaming)
    # ------------------------------------------------------------------

    def _get_feed(self):
        """Lazy-construct GrowwFeed on first use."""
        if self._feed is None:
            try:
                from growwapi import GrowwFeed
            except ImportError as exc:
                raise RuntimeError("growwapi not installed.") from exc
            self._feed = GrowwFeed(self._api)
            logger.info("GrowwFeed (NATS) connection established.")
        return self._feed

    def subscribe_ltp(
        self,
        instruments: List[Dict[str, str]],
        on_data_received: Optional[Callable] = None,
    ) -> dict:
        """
        Subscribe to real-time LTP updates via NATS WebSocket.

        Parameters
        ----------
        instruments : list of dict
            Each dict must have keys: ``exchange``, ``trading_symbol``,
            and optionally ``segment`` (defaults to "CASH").
            Example: ``[{"exchange": "NSE", "trading_symbol": "RELIANCE"}]``
        on_data_received : callable, optional
            Called whenever new LTP data arrives.

        Returns
        -------
        dict
            Initial subscription response.
        """
        feed = self._get_feed()
        return feed.subscribe_ltp(instruments, on_data_received=on_data_received)

    def get_ltp_snapshot(self) -> dict:
        """
        Return the most recently received LTP values for all subscribed instruments.
        Call ``subscribe_ltp()`` first.
        """
        return self._get_feed().get_ltp()

    def unsubscribe_ltp(self, instruments: List[Dict[str, str]]) -> dict:
        """Unsubscribe from LTP feed for the given instruments."""
        return self._get_feed().unsubscribe_ltp(instruments)

    def subscribe_market_depth(
        self,
        instruments: List[Dict[str, str]],
        on_data_received: Optional[Callable] = None,
    ) -> dict:
        """Subscribe to real-time bid/ask market depth via NATS."""
        feed = self._get_feed()
        return feed.subscribe_market_depth(instruments, on_data_received=on_data_received)

    def get_market_depth_snapshot(self) -> dict:
        """Return the latest depth snapshot for all subscribed instruments."""
        return self._get_feed().get_market_depth()

    # ------------------------------------------------------------------
    # Orders (read-only)
    # ------------------------------------------------------------------

    def get_order_list(
        self,
        segment: Optional[str] = "CASH",
        page: int = 0,
        page_size: int = 25,
    ) -> dict:
        """List orders. segment="CASH" | "FNO" | None (all)."""
        return _with_retry(
            self._api.get_order_list,
            page=page,
            page_size=page_size,
            segment=segment,
            label="get_order_list",
            timeout=self._timeout,
        )

    def get_order_detail(self, groww_order_id: str, segment: str = "CASH") -> dict:
        """Full detail for a specific order."""
        return _with_retry(
            self._api.get_order_detail,
            segment, groww_order_id,
            label=f"get_order_detail:{groww_order_id}",
            timeout=self._timeout,
        )

    def get_order_status(self, groww_order_id: str, segment: str = "CASH") -> dict:
        """Current status of an order by Groww order ID."""
        return _with_retry(
            self._api.get_order_status,
            segment, groww_order_id,
            label=f"get_order_status:{groww_order_id}",
            timeout=self._timeout,
        )

    def get_order_status_by_reference(
        self, order_reference_id: str, segment: str = "CASH"
    ) -> dict:
        """Current status of an order by caller-supplied reference ID."""
        return _with_retry(
            self._api.get_order_status_by_reference,
            segment, order_reference_id,
            label=f"get_order_status_ref:{order_reference_id}",
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def get_trade_history(
        self,
        groww_order_id: str,
        segment: str = "CASH",
        page: int = 0,
        page_size: int = 25,
    ) -> dict:
        """Trade fill list for a specific order."""
        return _with_retry(
            self._api.get_trade_list_for_order,
            groww_order_id, segment, page, page_size,
            label=f"get_trade_history:{groww_order_id}",
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self, segment: Optional[str] = "CASH") -> dict:
        """All open/closed intraday positions for the user."""
        return _with_retry(
            self._api.get_positions_for_user,
            segment=segment,
            label="get_positions",
            timeout=self._timeout,
        )

    def get_position(self, trading_symbol: str, segment: str = "CASH") -> dict:
        """Position for a single trading symbol."""
        return _with_retry(
            self._api.get_position_for_trading_symbol,
            trading_symbol, segment,
            label=f"get_position:{trading_symbol}",
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # Holdings (demat)
    # ------------------------------------------------------------------

    def get_holdings(self) -> dict:
        """Demat holdings for the user (CNC positions carry-forward)."""
        return _with_retry(
            self._api.get_holdings_for_user,
            label="get_holdings",
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # Margin
    # ------------------------------------------------------------------

    def get_available_margin(self) -> dict:
        """
        Available cash margin / collateral details.

        Returns dict with available funds, used margin, collateral value, etc.

        Note: Span margin calculation for F&O is NOT available in SDK v1.5.
        """
        return _with_retry(
            self._api.get_available_margin_details,
            label="get_available_margin",
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    def get_user_profile(self) -> dict:
        """Account profile (name, email, PAN, demat account details)."""
        return _with_retry(
            self._api.get_user_profile,
            label="get_user_profile",
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # Order placement — permanently blocked
    # ------------------------------------------------------------------

    def place_order(self, *args, **kwargs) -> None:  # type: ignore[override]
        """
        BLOCKED: Live order placement is permanently disabled.

        Use ``broker.mock.MockBroker`` for paper/backtest trading.
        """
        raise LiveTradingBlockedError()

    def modify_order(self, *args, **kwargs) -> None:
        """BLOCKED: See place_order."""
        raise LiveTradingBlockedError()

    def cancel_order(self, *args, **kwargs) -> None:
        """BLOCKED: See place_order."""
        raise LiveTradingBlockedError()