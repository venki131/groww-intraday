"""
Abstract Broker Interface.

All broker implementations (Groww, Mock) must implement AbstractBroker.
Strategy logic depends only on this interface - never on concrete broker classes.
This enables full testability via MockBroker without any network calls.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class OrderType(str, Enum):
    """Supported order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class TransactionType(str, Enum):
    """Trade direction."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order lifecycle states."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class ProductType(str, Enum):
    """NSE product type for intraday."""
    MIS = "MIS"   # Margin Intraday Squareoff
    CNC = "CNC"   # Cash and Carry (delivery)
    NRML = "NRML"


# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------


@dataclass
class Quote:
    """Real-time market quote for a symbol."""

    ticker: str
    exchange: str
    last_price: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    timestamp: datetime
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    vwap: Optional[Decimal] = None


@dataclass
class Candle:
    """OHLCV candle bar."""

    ticker: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    interval_minutes: int = 5
    vwap: Optional[Decimal] = None


@dataclass
class OrderRequest:
    """
    Immutable order placement request.

    Strategy code constructs this; broker places it.
    """

    ticker: str
    transaction_type: TransactionType
    quantity: int
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.MIS
    price: Optional[Decimal] = None          # Required for LIMIT orders
    trigger_price: Optional[Decimal] = None  # Required for SL orders
    exchange: str = "NSE"
    tag: Optional[str] = None                # Strategy name or signal tag


@dataclass
class OrderResponse:
    """Result returned after placing an order."""

    broker_order_id: str
    ticker: str
    transaction_type: TransactionType
    quantity: int
    status: OrderStatus
    average_price: Optional[Decimal] = None
    filled_quantity: int = 0
    rejection_reason: Optional[str] = None
    placed_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None


@dataclass
class Position:
    """Current open position snapshot."""

    ticker: str
    quantity: int
    average_buy_price: Decimal
    current_price: Decimal
    unrealised_pnl: Decimal
    product_type: ProductType = ProductType.MIS


@dataclass
class AccountInfo:
    """Broker account / margin information."""

    client_id: str
    available_cash: Decimal
    used_margin: Decimal
    total_margin: Decimal
    positions: List[Position] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract Broker
# ---------------------------------------------------------------------------


class AbstractBroker(ABC):
    """
    Abstract base class for all broker integrations.

    Implementations:
    - GrowwBroker  : Real Groww API (paper trading only)
    - MockBroker   : In-memory fake for unit tests

    Strategy logic must depend only on this interface.
    """

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    @abstractmethod
    async def login(self) -> bool:
        """
        Authenticate with the broker.

        Returns:
            True if login succeeded.

        Raises:
            BrokerAuthError: If authentication fails.
        """
        ...

    @abstractmethod
    async def logout(self) -> None:
        """Terminate the broker session."""
        ...

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Return True if the broker session is active."""
        ...

    # ------------------------------------------------------------------
    # Market Data
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_quote(self, ticker: str, exchange: str = "NSE") -> Quote:
        """
        Fetch real-time quote for a symbol.

        Args:
            ticker: NSE symbol (e.g. 'RELIANCE').
            exchange: Exchange code (default 'NSE').

        Returns:
            Quote dataclass.

        Raises:
            BrokerDataError: On API failure.
        """
        ...

    @abstractmethod
    async def get_candles(
        self,
        ticker: str,
        interval_minutes: int = 5,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        exchange: str = "NSE",
    ) -> List[Candle]:
        """
        Fetch historical OHLCV candles.

        Args:
            ticker: NSE symbol.
            interval_minutes: Candle interval in minutes.
            from_dt: Start datetime (IST).
            to_dt: End datetime (IST).
            exchange: Exchange code.

        Returns:
            List of Candle objects ordered by timestamp ascending.
        """
        ...

    # ------------------------------------------------------------------
    # Order Management
    # ------------------------------------------------------------------

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """
        Place an order.

        Args:
            request: Fully populated OrderRequest.

        Returns:
            OrderResponse with broker_order_id and initial status.

        Raises:
            LiveTradingBlockedError: If live trading is attempted.
            BrokerOrderError: On order placement failure.
        """
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            broker_order_id: Broker-assigned order ID.

        Returns:
            True if cancellation was accepted.
        """
        ...

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> OrderResponse:
        """
        Fetch current status of an order.

        Args:
            broker_order_id: Broker-assigned order ID.

        Returns:
            Updated OrderResponse.
        """
        ...

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Return all current open positions.

        Returns:
            List of Position objects.
        """
        ...

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """
        Return account balance and margin details.

        Returns:
            AccountInfo dataclass.
        """
        ...


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class BrokerError(Exception):
    """Base exception for all broker errors."""


class BrokerAuthError(BrokerError):
    """Raised when broker authentication fails."""


class BrokerDataError(BrokerError):
    """Raised when market data fetch fails."""


class BrokerOrderError(BrokerError):
    """Raised when order placement or management fails."""


class LiveTradingBlockedError(BrokerError):
    """
    Raised if any code path attempts live order placement.

    This is a hard safety guard - live trading is permanently disabled.
    """