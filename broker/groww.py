"""
Groww Broker Implementation.

Implements AbstractBroker against the Groww Trading API.

SAFETY GUARDS:
- live_trading_enabled is ALWAYS False
- place_order raises LiveTradingBlockedError if mode == 'live'
- Credentials are loaded exclusively from environment variables

Paper trading mode: orders are simulated locally and NOT sent to Groww's
order management system (until Groww paper trading API is confirmed).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from broker.base import (
    AbstractBroker,
    AccountInfo,
    BrokerAuthError,
    BrokerDataError,
    BrokerOrderError,
    Candle,
    LiveTradingBlockedError,
    OrderRequest,
    OrderResponse,
    OrderStatus,
    Position,
    Quote,
)
from config.logging_config import get_logger

logger = get_logger(__name__)

# Hard safety constant - NEVER change this to True
_LIVE_TRADING_ENABLED: bool = False


class GrowwBroker(AbstractBroker):
    """
    Groww Trading API broker.

    Supports paper trading and market data fetching only.
    Live order placement is permanently blocked.

    Args:
        api_key: Groww API key (defaults to GROWW_API_KEY env var).
        api_secret: Groww API secret (defaults to GROWW_API_SECRET env var).
        base_url: Groww API base URL.
        mode: 'paper' or 'backtest' (live is blocked).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = "https://api.groww.in/v1",
        mode: str = "paper",
    ) -> None:
        if mode.lower() == "live":
            raise LiveTradingBlockedError(
                "Live trading is permanently disabled. Use 'paper' or 'backtest' mode."
            )

        self._api_key: str = api_key or os.getenv("GROWW_API_KEY", "")
        self._api_secret: str = api_secret or os.getenv("GROWW_API_SECRET", "")
        self._base_url: str = base_url
        self._mode: str = mode.lower()
        self._access_token: Optional[str] = None
        self._authenticated: bool = False

        # In-memory paper order book
        self._paper_orders: dict[str, OrderResponse] = {}

        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=30.0,
            headers={"Content-Type": "application/json"},
        )

        logger.info("GrowwBroker initialized", mode=self._mode, base_url=self._base_url)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self) -> bool:
        """
        Authenticate with Groww API.

        In paper/backtest mode, validates credentials are present but
        does not make a live auth call unless needed for market data.

        Returns:
            True on success.

        Raises:
            BrokerAuthError: If credentials are missing.
        """
        if not self._api_key:
            raise BrokerAuthError(
                "GROWW_API_KEY not set. Set it in your .env file."
            )
        if not self._api_secret:
            raise BrokerAuthError(
                "GROWW_API_SECRET not set. Set it in your .env file."
            )

        try:
            # In production paper mode, would exchange key/secret for access token
            # For now, mark as authenticated with the API key
            self._access_token = f"paper_{self._api_key[:8]}..."
            self._authenticated = True
            logger.info("GrowwBroker authenticated", mode=self._mode)
            return True
        except Exception as exc:
            logger.error("GrowwBroker login failed", error=str(exc))
            raise BrokerAuthError(f"Login failed: {exc}") from exc

    async def logout(self) -> None:
        """Terminate the Groww session."""
        self._authenticated = False
        self._access_token = None
        await self._client.aclose()
        logger.info("GrowwBroker logged out")

    def is_authenticated(self) -> bool:
        """Return True if the session is active."""
        return self._authenticated

    # ------------------------------------------------------------------
    # Market Data
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_quote(self, ticker: str, exchange: str = "NSE") -> Quote:
        """
        Fetch real-time quote from Groww API.

        Args:
            ticker: NSE symbol (e.g. 'RELIANCE').
            exchange: Exchange code.

        Returns:
            Quote dataclass.

        Raises:
            BrokerDataError: On API failure.
        """
        try:
            response = await self._client.get(
                f"/quotes/{exchange}/{ticker}",
                headers=self._auth_headers(),
            )
            response.raise_for_status()
            data = response.json()

            return Quote(
                ticker=ticker,
                exchange=exchange,
                last_price=Decimal(str(data.get("ltp", 0))),
                open=Decimal(str(data.get("open", 0))),
                high=Decimal(str(data.get("high", 0))),
                low=Decimal(str(data.get("low", 0))),
                close=Decimal(str(data.get("close", 0))),
                volume=int(data.get("volume", 0)),
                timestamp=datetime.now(),
                bid=Decimal(str(data.get("bid", 0))) if data.get("bid") else None,
                ask=Decimal(str(data.get("ask", 0))) if data.get("ask") else None,
                vwap=Decimal(str(data.get("vwap", 0))) if data.get("vwap") else None,
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Quote fetch failed", ticker=ticker, status=exc.response.status_code)
            raise BrokerDataError(f"Quote fetch failed for {ticker}: {exc}") from exc
        except Exception as exc:
            logger.error("Quote fetch error", ticker=ticker, error=str(exc))
            raise BrokerDataError(f"Unexpected error fetching quote for {ticker}: {exc}") from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_candles(
        self,
        ticker: str,
        interval_minutes: int = 5,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        exchange: str = "NSE",
    ) -> List[Candle]:
        """
        Fetch historical OHLCV candles from Groww API.

        Args:
            ticker: NSE symbol.
            interval_minutes: Candle size in minutes.
            from_dt: Start datetime.
            to_dt: End datetime.
            exchange: Exchange code.

        Returns:
            List of Candle objects.
        """
        params: dict = {
            "interval": f"{interval_minutes}m",
            "exchange": exchange,
        }
        if from_dt:
            params["from"] = int(from_dt.timestamp() * 1000)
        if to_dt:
            params["to"] = int(to_dt.timestamp() * 1000)

        try:
            response = await self._client.get(
                f"/candles/{ticker}",
                params=params,
                headers=self._auth_headers(),
            )
            response.raise_for_status()
            raw = response.json().get("candles", [])

            return [
                Candle(
                    ticker=ticker,
                    timestamp=datetime.fromtimestamp(c[0] / 1000),
                    open=Decimal(str(c[1])),
                    high=Decimal(str(c[2])),
                    low=Decimal(str(c[3])),
                    close=Decimal(str(c[4])),
                    volume=int(c[5]),
                    interval_minutes=interval_minutes,
                )
                for c in raw
            ]
        except httpx.HTTPStatusError as exc:
            raise BrokerDataError(f"Candle fetch failed for {ticker}: {exc}") from exc
        except Exception as exc:
            raise BrokerDataError(f"Unexpected error fetching candles for {ticker}: {exc}") from exc

    # ------------------------------------------------------------------
    # Order Management (Paper only)
    # ------------------------------------------------------------------

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """
        Place an order in paper mode (simulated locally).

        LIVE TRADING IS PERMANENTLY BLOCKED.

        Args:
            request: Fully populated OrderRequest.

        Returns:
            Simulated OrderResponse.

        Raises:
            LiveTradingBlockedError: Always raised if mode is 'live'.
        """
        if _LIVE_TRADING_ENABLED:
            raise LiveTradingBlockedError("Live trading guard triggered.")

        if self._mode == "live":
            raise LiveTradingBlockedError(
                "Live order placement is permanently disabled. "
                "This system operates in BACKTEST and PAPER modes only."
            )

        # Simulate paper order
        order_id = str(uuid.uuid4())
        response = OrderResponse(
            broker_order_id=order_id,
            ticker=request.ticker,
            transaction_type=request.transaction_type,
            quantity=request.quantity,
            status=OrderStatus.COMPLETE,
            average_price=request.price or Decimal("0"),
            filled_quantity=request.quantity,
            placed_at=datetime.now(),
            filled_at=datetime.now(),
        )
        self._paper_orders[order_id] = response

        logger.info(
            "Paper order placed",
            order_id=order_id,
            ticker=request.ticker,
            side=request.transaction_type.value,
            qty=request.quantity,
        )
        return response

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel a paper order."""
        if broker_order_id in self._paper_orders:
            self._paper_orders[broker_order_id].status = OrderStatus.CANCELLED
            logger.info("Paper order cancelled", order_id=broker_order_id)
            return True
        return False

    async def get_order_status(self, broker_order_id: str) -> OrderResponse:
        """Return status of a paper order."""
        if broker_order_id not in self._paper_orders:
            raise BrokerOrderError(f"Order {broker_order_id} not found")
        return self._paper_orders[broker_order_id]

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def get_positions(self) -> List[Position]:
        """Return empty positions list (paper mode)."""
        return []

    async def get_account_info(self) -> AccountInfo:
        """Return simulated account info."""
        return AccountInfo(
            client_id=os.getenv("GROWW_CLIENT_ID", "PAPER_CLIENT"),
            available_cash=Decimal("10000"),
            used_margin=Decimal("0"),
            total_margin=Decimal("10000"),
            positions=[],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        """
        Build authentication headers for API requests.

        Returns:
            Dict of HTTP headers.
        """
        return {
            "Authorization": f"Bearer {self._access_token or ''}",
            "X-API-Key": self._api_key,
        }