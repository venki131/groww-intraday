"""Tests for RiskManager."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from risk.manager import RiskManager
from strategies.base import Signal, SignalType


def _buy_signal(price: Decimal = Decimal("1000"),
                stop_loss: Decimal | None = Decimal("985")) -> Signal:
    return Signal(
        ticker="RELIANCE", signal_type=SignalType.BUY,
        price=price, timestamp=datetime.now(),
        strategy_name="test", stop_loss=stop_loss,
        take_profit=Decimal("1030"),
    )


def test_risk_check_approved(risk_manager: RiskManager) -> None:
    result = risk_manager.validate_signal(_buy_signal())
    assert result.approved
    assert result.adjusted_quantity > 0
    assert result.adjusted_stop_loss is not None


def test_risk_blocks_when_daily_loss_hit() -> None:
    rm = RiskManager(capital=Decimal("10000"), max_daily_loss_pct=3.0)
    rm.update_daily_pnl(Decimal("-310"))  # > 3% of 10000
    result = rm.validate_signal(_buy_signal())
    assert not result.approved
    assert "daily loss" in result.reason.lower()


def test_risk_blocks_max_positions() -> None:
    rm = RiskManager(capital=Decimal("10000"), max_open_positions=2)
    rm.open_position()
    rm.open_position()
    result = rm.validate_signal(_buy_signal())
    assert not result.approved
    assert "max open" in result.reason.lower()


def test_risk_blocks_duplicate_position() -> None:
    result = RiskManager().validate_signal(
        _buy_signal(), current_positions=["RELIANCE"]
    )
    assert not result.approved


def test_risk_uses_default_stop_loss_when_none() -> None:
    """Signal with no stop_loss should still pass using default SL."""
    rm = RiskManager(capital=Decimal("10000"), stop_loss_pct=1.5)
    signal = _buy_signal(stop_loss=None)
    result = rm.validate_signal(signal)
    assert result.approved
    assert result.adjusted_stop_loss is not None


def test_risk_quantity_respects_capital(risk_manager: RiskManager) -> None:
    result = risk_manager.validate_signal(_buy_signal(price=Decimal("5000")))
    if result.approved:
        trade_value = Decimal(str(result.adjusted_quantity)) * Decimal("5000")
        # Must not exceed 20% of 10000 = 2000
        assert trade_value <= Decimal("2000")


def test_risk_is_trading_allowed(risk_manager: RiskManager) -> None:
    assert risk_manager.is_trading_allowed is True
    risk_manager.update_daily_pnl(Decimal("-400"))  # > 3%
    assert risk_manager.is_trading_allowed is False


def test_risk_reset(risk_manager: RiskManager) -> None:
    risk_manager.open_position()
    risk_manager.update_daily_pnl(Decimal("-200"))
    risk_manager.reset_daily()
    assert risk_manager.daily_pnl == Decimal("0")
    assert risk_manager.open_positions_count == 0


def test_risk_open_close_tracking(risk_manager: RiskManager) -> None:
    assert risk_manager.open_positions_count == 0
    risk_manager.open_position()
    assert risk_manager.open_positions_count == 1
    risk_manager.close_position()
    assert risk_manager.open_positions_count == 0