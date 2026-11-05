"""
Mock Broker Implementation for Unit Testing.

Provides a fully controllable in-memory broker that:
- Requires no network calls
- Supports scenario injection (order failures, price sequences)
- Tracks all calls for assertion in tests
- Implements the full AbstractBroker interface

Usage in tests:
    broker = MockBroker(initial_price={"RELIANCE": Decimal("2500")})
    await broker.login()
    response = await broker.place_order(request)
    assert broker.orders_placed[0].ticker == "RELIANCE"
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from broker.base import (
    AbstractBroker,
    AccountInfo,
    BrokerAuthError,
    BrokerOrderError,
    Candle,
    LiveTradingBlockedError,
    OrderRequest,
    OrderResponse,
    OrderStatus,
    Position,
    Quote,
    TransactionType,
)
from config.logging_config import get_logger

logger = get_logger(__name__)


class MockBroker(AbstractBroker):
    """
    In-memory mock broker for testing strategies without network calls.

    Attributes:
        orders_placed: List of all OrderRequest objects received.
        order_responses: Pre-configured responses for place_order.
        candle_data: Pre-loaded candle sequences per ticker.
        quote_data: Pre-loaded quotes per ticker.
        should_fail_login: If True, login() raises BrokerAuthError.
        should_fail_orders: If True, place_order() raises BrokerOrderError.
        available_cash: Simulated account balance.
    """

    def __init__(
        self,
        initial_prices: Optional[Dict[str, Decimal]] = None,
        available_cash: Decimal = Decimal("10000"),
        should_fail_login: bool = False,
        should_fail_orders: bool = False,
        mode: str = "backtest",
    ) -> None:
        self._authenticated: bool = False
        self._mode: str = mode
        self.available_cash: Decimal = available_cash
        self.should_fail_login: bool = should_fail_login
        self.should_fail_orders: bool = should_fail_orders

        # Tracking
        self.orders_placed: List[OrderRequest] = []
        self.orders_cancelled: List[str] = []
        self.login_called: int = 0
        self.logout_called: int = 0

        # Data stores
        self._prices: Dict[str, Decimal] = initial_prices or {}
        self._candles: Dict[str, List[Candle]] = {}
        self._order_book: Dict[str, OrderResponse] = {}
        self._positions: List[Position] = []

    # ------------------------------------------------------------------
    # Setup helpers (call from test fixtures)
    # ------------------------------------------------------------------

    def set_price(self, ticker: str, price: Decimal) -> None:
        """
        Set the mock LTP for a symbol.

        Args:
            ticker: NSE symbol.
            price: Price to return for quotes.
        """
        self._prices[ticker] = price

    def set_candles(self, ticker: str, candles: List[Candle]) -> None:
        """
        Pre-load candle data for a symbol.

        Args:
            ticker: NSE symbol.
            candles: List of Candle objects to return for get_candles().
        """
        self._candles[ticker] = candles

    def add_position(self, position: Position) -> None:
        """Add a mock open position."""
        self._positions.append(position)

    def generate_candles(
        self,
        ticker: str,
        count: int = 50,
        base_price: Decimal = Decimal("1000"),
        interval_minutes: int = 5,
    ) -> List[Candle]:
        """
        Generate synthetic OHLCV candles for a ticker.

        Args:
            ticker: NSE symbol.
            count: Number of candles to generate.
            base_price: Starting price.
            interval_minutes: Candle interval.

        Returns:
            List of generated Candle objects (also stored internally).
        """
        import random
        random.seed(42)

        candles: List[Candle] = []
        price = float(base_price)
        start_time = datetime(2023, 6, 1, 9, 15, 0)

        for i in range(count):
            change_pct = random.uniform(-0.005, 0.005)
            open_p = price
            close_p = price * (1 + change_pct)
            high_p = max(open_p, close_p) * random.uniform(1.0, 1.003)
            low_p = min(open_p, close_p) * random.uniform(0.997, 1.0)
            volume = random.randint(5000, 50000)

            candles.append(
                Candle(
                    ticker=ticker,
                    timestamp=start_time + timedelta(minutes=i * interval_minutes),
                    open=Decimal(str(round(open_p, 2))),
                    high=Decimal(str(round(high_p, 2))),
                    low=Decimal(str(round(low_p, 2))),
                    close=Decimal(str(round(close_p, 2))),
                    volume=volume,
                    interval_minutes=interval_minutes,
                )
            )
            price = close_p

        self._candles[ticker] = candles
        self._prices[ticker] = Decimal(str(round(price, 2)))
        return candles

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self) -> bool:
        """Simulate login. Raises BrokerAuthError if should_fail_login=True."""
        self.login_called += 1
        if self.should_fail_login:
            raise BrokerAuthError("Mock login failure (should_fail_login=True)")
        self._authenticated = True
        logger.debug("MockBroker: login successful")
        return True

    async def logout(self) -> None:
        """Simulate logout."""
        self.logout_called += 1
        self._authenticated = False
        logger.debug("MockBroker: logout")

    def is_authenticated(self) -> bool:
        return self._authenticated

    # ------------------------------------------------------------------
    # Market Data
    # ------------------------------------------------------------------

    async def get_quote(self, ticker: str, exchange: str = "NSE") -> Quote:
        """
        Return a mock quote.

        Uses price set via set_price() or defaults to 1000.

        Args:
            ticker: NSE symbol.
            exchange: Exchange code (ignored in mock).

        Returns:
            Quote with mocked values.
        """
        price = self._prices.get(ticker, Decimal("1000"))
        return Quote(
            ticker=ticker,
            exchange=exchange,
            last_price=price,
            open=price * Decimal("0.99"),
            high=price * Decimal("1.01"),
            low=price * Decimal("0.98"),
            close=price,
            volume=100000,
            timestamp=datetime.now(),
            bid=price - Decimal("0.05"),
            ask=price + Decimal("0.05"),
            vwap=price,
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
        Return pre-loaded candles or auto-generate if not set.

        Args:
            ticker: NSE symbol.
            interval_minutes: Candle interval (used for auto-generation).
            from_dt: Optional start filter.
            to_dt: Optional end filter.
            exchange: Ignored in mock.

        Returns:
            List of Candle objects.
        """
        if ticker not in self._candles:
            self.generate_candles(ticker, interval_minutes=interval_minutes)

        candles = self._candles[ticker]

        # Apply date filters if provided
        if from_dt:
            candles = [c for c in candles if c.timestamp >= from_dt]
        if to_dt:
            candles = [c for c in candles if c.timestamp <= to_dt]

        return candles

    # ------------------------------------------------------------------
    # Order Management
    # ------------------------------------------------------------------

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """
        Simulate order placement.

        Records the request in orders_placed.
        Raises BrokerOrderError if should_fail_orders=True.

        Args:
            request: Order request from strategy.

        Returns:
            Simulated OrderResponse.

        Raises:
            LiveTradingBlockedError: If mode is 'live'.
            BrokerOrderError: If should_fail_orders=True.
        """
        if self._mode == "live":
            raise LiveTradingBlockedError("Mock broker blocks live trading.")

        self.orders_placed.append(request)

        if self.should_fail_orders:
            order_id = str(uuid.uuid4())
            response = OrderResponse(
                broker_order_id=order_id,
                ticker=request.ticker,
                transaction_type=request.transaction_type,
                quantity=request.quantity,
                status=OrderStatus.REJECTED,
                rejection_reason="Mock rejection (should_fail_orders=True)",
                placed_at=datetime.now(),
            )
            self._order_book[order_id] = response
            return response

        order_id = str(uuid.uuid4())
        fill_price = request.price or self._prices.get(request.ticker, Decimal("1000"))

        response = OrderResponse(
            broker_order_id=order_id,
            ticker=request.ticker,
            transaction_type=request.transaction_type,
            quantity=request.quantity,
            status=OrderStatus.COMPLETE,
            average_price=fill_price,
            filled_quantity=request.quantity,
            placed_at=datetime.now(),
            filled_at=datetime.now(),
        )
        self._order_book[order_id] = response

        # Update cash balance
        trade_value = fill_price * request.quantity
        if request.transaction_type == TransactionType.BUY:
            self.available_cash -= trade_value
        else:
            self.available_cash += trade_value

        logger.debug(
            "MockBroker: order placed",
            order_id=order_id,
            ticker=request.ticker,
            side=request.transaction_type.value,
        )
        return response

    async def cancel_order(self, broker_order_id: str) -> bool:
        """
        Cancel a mock order.

        Args:
            broker_order_id: Order ID to cancel.

        Returns:
            True if found and cancelled.
        """
        self.orders_cancelled.append(broker_order_id)
        if broker_order_id in self._order_book:
            self._order_book[broker_order_id].status = OrderStatus.CANCELLED
            return True
        return False

    async def get_order_status(self, broker_order_id: str) -> OrderResponse:
        """
        Return mock order status.

        Args:
            broker_order_id: Order ID.

        Returns:
            OrderResponse.

        Raises:
            BrokerOrderError: If order ID not found.
        """
        if broker_order_id not in self._order_book:
            raise BrokerOrderError(f"Mock order {broker_order_id} not found")
        return self._order_book[broker_order_id]

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def get_positions(self) -> List[Position]:
        """Return mock positions."""
        return list(self._positions)

    async def get_account_info(self) -> AccountInfo:
        """Return mock account info with current cash balance."""
        return AccountInfo(
            client_id="MOCK_CLIENT_001",
            available_cash=self.available_cash,
            used_margin=Decimal("0"),
            total_margin=self.available_cash,
            positions=list(self._positions),
        )

    # ------------------------------------------------------------------
    # Test assertion helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all tracking state between tests."""
        self.orders_placed.clear()
        self.orders_cancelled.clear()
        self._order_book.clear()
        self._positions.clear()
        self.login_called = 0
        self.logout_called = 0
        self._authenticated = False

    @property
    def buy_orders(self) -> List[OrderRequest]:
        """Return only BUY orders placed."""
        return [o for o in self.orders_placed if o.transaction_type == TransactionType.BUY]

    @property
    def sell_orders(self) -> List[OrderRequest]:
        """Return only SELL orders placed."""
        return [o for o in self.orders_placed if o.transaction_type == TransactionType.SELL]