"""Tests for MockBroker and broker safety guards."""

from __future__ import annotations

from decimal import Decimal

import pytest

from broker.base import LiveTradingBlockedError, OrderRequest, OrderStatus, TransactionType, OrderType
from broker.mock import MockBroker


@pytest.mark.asyncio
async def test_mock_broker_login(mock_broker: MockBroker) -> None:
    result = await mock_broker.login()
    assert result is True
    assert mock_broker.is_authenticated()
    assert mock_broker.login_called == 1


@pytest.mark.asyncio
async def test_mock_broker_login_failure() -> None:
    broker = MockBroker(should_fail_login=True)
    from broker.base import BrokerAuthError
    with pytest.raises(BrokerAuthError):
        await broker.login()


@pytest.mark.asyncio
async def test_mock_broker_place_order(mock_broker: MockBroker) -> None:
    await mock_broker.login()
    request = OrderRequest(
        ticker="RELIANCE",
        transaction_type=TransactionType.BUY,
        quantity=5,
        order_type=OrderType.MARKET,
    )
    response = await mock_broker.place_order(request)

    assert response.status == OrderStatus.COMPLETE
    assert response.filled_quantity == 5
    assert response.ticker == "RELIANCE"
    assert len(mock_broker.orders_placed) == 1


@pytest.mark.asyncio
async def test_mock_broker_buy_sell_tracking(mock_broker: MockBroker) -> None:
    await mock_broker.login()
    buy_req = OrderRequest("RELIANCE", TransactionType.BUY, 10, OrderType.MARKET)
    sell_req = OrderRequest("RELIANCE", TransactionType.SELL, 10, OrderType.MARKET)

    await mock_broker.place_order(buy_req)
    await mock_broker.place_order(sell_req)

    assert len(mock_broker.buy_orders) == 1
    assert len(mock_broker.sell_orders) == 1


@pytest.mark.asyncio
async def test_live_trading_blocked() -> None:
    """Live mode must always be blocked."""
    with pytest.raises(LiveTradingBlockedError):
        MockBroker(mode="live")


@pytest.mark.asyncio
async def test_order_rejection(mock_broker: MockBroker) -> None:
    broker = MockBroker(should_fail_orders=True)
    await broker.login()
    request = OrderRequest("TCS", TransactionType.BUY, 1, OrderType.MARKET)
    response = await broker.place_order(request)
    assert response.status == OrderStatus.REJECTED
    assert response.rejection_reason is not None


@pytest.mark.asyncio
async def test_cancel_order(mock_broker: MockBroker) -> None:
    await mock_broker.login()
    request = OrderRequest("INFY", TransactionType.BUY, 2, OrderType.MARKET)
    response = await mock_broker.place_order(request)

    cancelled = await mock_broker.cancel_order(response.broker_order_id)
    assert cancelled is True
    status = await mock_broker.get_order_status(response.broker_order_id)
    assert status.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_get_quote(mock_broker: MockBroker) -> None:
    quote = await mock_broker.get_quote("RELIANCE")
    assert quote.ticker == "RELIANCE"
    assert quote.last_price > 0


@pytest.mark.asyncio
async def test_get_candles(mock_broker: MockBroker) -> None:
    candles = await mock_broker.get_candles("RELIANCE")
    assert len(candles) >= 50
    assert candles[0].ticker == "RELIANCE"
    assert candles[0].open > 0


@pytest.mark.asyncio
async def test_cash_decrements_on_buy(mock_broker: MockBroker) -> None:
    await mock_broker.login()
    initial_cash = mock_broker.available_cash
    request = OrderRequest(
        "RELIANCE", TransactionType.BUY, 1, OrderType.MARKET,
        price=Decimal("2500"),
    )
    await mock_broker.place_order(request)
    assert mock_broker.available_cash < initial_cash


@pytest.mark.asyncio
async def test_broker_reset(mock_broker: MockBroker) -> None:
    await mock_broker.login()
    await mock_broker.place_order(
        OrderRequest("RELIANCE", TransactionType.BUY, 1, OrderType.MARKET)
    )
    mock_broker.reset()
    assert len(mock_broker.orders_placed) == 0
    assert mock_broker.login_called == 0
    assert not mock_broker.is_authenticated()