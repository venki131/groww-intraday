"""Portfolio manager - tracks cash, positions, and P&L."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PositionRecord:
    ticker: str
    quantity: int
    avg_buy_price: Decimal
    current_price: Decimal = Decimal("0")
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    strategy_name: str = ""
    opened_at: datetime = field(default_factory=datetime.now)

    @property
    def market_value(self) -> Decimal:
        return self.current_price * self.quantity

    @property
    def unrealised_pnl(self) -> Decimal:
        return (self.current_price - self.avg_buy_price) * self.quantity


@dataclass
class PortfolioSnapshot:
    timestamp: datetime
    cash: Decimal
    positions: List[PositionRecord]
    realised_pnl: Decimal

    @property
    def total_equity(self) -> Decimal:
        return self.cash + sum(p.market_value for p in self.positions)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cash": float(self.cash),
            "total_equity": float(self.total_equity),
            "realised_pnl": float(self.realised_pnl),
            "unrealised_pnl": float(sum(p.unrealised_pnl for p in self.positions)),
            "positions": [
                {"ticker": p.ticker, "qty": p.quantity,
                 "avg_buy": float(p.avg_buy_price), "current": float(p.current_price),
                 "pnl": float(p.unrealised_pnl)}
                for p in self.positions
            ],
        }


class PortfolioManager:
    """
    Paper/backtest portfolio tracker.

    Args:
        initial_capital: Starting cash in INR.
        commission_pct: Per-trade commission as percentage.
    """

    def __init__(self, initial_capital: Decimal = Decimal("10000"),
                 commission_pct: float = 0.03) -> None:
        self.initial_capital = initial_capital
        self.cash: Decimal = initial_capital
        self.commission_pct = commission_pct
        self._positions: Dict[str, PositionRecord] = {}
        self._realised_pnl: Decimal = Decimal("0")

    def open_position(self, ticker: str, quantity: int, price: Decimal,
                      stop_loss: Optional[Decimal] = None,
                      take_profit: Optional[Decimal] = None,
                      strategy_name: str = "") -> bool:
        """Open a new long position. Returns False if insufficient cash."""
        total_cost = price * quantity * Decimal(str(1 + self.commission_pct / 100))
        if total_cost > self.cash:
            logger.warning("Insufficient cash", ticker=ticker, required=float(total_cost))
            return False
        self._positions[ticker] = PositionRecord(
            ticker=ticker, quantity=quantity, avg_buy_price=price,
            current_price=price, stop_loss=stop_loss,
            take_profit=take_profit, strategy_name=strategy_name,
        )
        self.cash -= total_cost
        logger.info("Position opened", ticker=ticker, qty=quantity, price=float(price))
        return True

    def close_position(self, ticker: str, price: Decimal) -> Optional[Decimal]:
        """Close position fully. Returns net P&L or None if ticker not held."""
        if ticker not in self._positions:
            return None
        pos = self._positions.pop(ticker)
        proceeds = price * pos.quantity
        commission = proceeds * Decimal(str(self.commission_pct / 100))
        net_pnl = (price - pos.avg_buy_price) * pos.quantity - commission
        self.cash += proceeds - commission
        self._realised_pnl += net_pnl
        logger.info("Position closed", ticker=ticker, net_pnl=float(net_pnl))
        return net_pnl

    def update_prices(self, prices: Dict[str, Decimal]) -> None:
        for ticker, price in prices.items():
            if ticker in self._positions:
                self._positions[ticker].current_price = price

    def get_snapshot(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            timestamp=datetime.now(), cash=self.cash,
            positions=list(self._positions.values()),
            realised_pnl=self._realised_pnl,
        )

    @property
    def open_tickers(self) -> List[str]:
        return list(self._positions.keys())

    @property
    def total_equity(self) -> Decimal:
        return self.cash + sum(p.market_value for p in self._positions.values())