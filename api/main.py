"""
FastAPI application entry point.

Endpoints:
  GET  /health                  - Service health check
  GET  /api/v1/universe         - Nifty 100 symbols
  POST /api/v1/backtest         - Run a backtest
  GET  /api/v1/portfolio        - Portfolio snapshot
  GET  /api/v1/market/status    - Market open/closed status
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config.logging_config import get_logger, setup_logging
from database.connection import check_database_health
from market.hours import is_market_open, is_trading_allowed
from market.universe import NIFTY100_SYMBOLS

setup_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="Groww Intraday Automation API",
    description="Backtest and paper trading system for NSE Nifty 100 equities.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    ticker: str = Field(..., description="NSE symbol e.g. RELIANCE")
    strategy: str = Field(default="ema_crossover", description="Strategy name")
    start_date: str = Field(default="2023-01-01", description="YYYY-MM-DD")
    end_date: str = Field(default="2023-12-31", description="YYYY-MM-DD")
    initial_capital: float = Field(default=10000.0, ge=1000)
    fast_period: int = Field(default=9, ge=2)
    slow_period: int = Field(default=21, ge=5)


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Check API and database health."""
    db_health = await check_database_health()
    return HealthResponse(
        status="ok" if db_health["status"] == "ok" else "degraded",
        database=db_health["detail"],
    )


@app.get("/api/v1/universe", tags=["Market"])
async def get_universe() -> dict:
    """Return all Nifty 100 symbols."""
    return {"symbols": NIFTY100_SYMBOLS, "count": len(NIFTY100_SYMBOLS)}


@app.get("/api/v1/market/status", tags=["Market"])
async def market_status() -> dict:
    """Return current NSE market open/closed status."""
    return {
        "is_open": is_market_open(),
        "is_trading_allowed": is_trading_allowed(),
        "exchange": "NSE",
    }


@app.post("/api/v1/backtest", tags=["Backtest"])
async def run_backtest(request: BacktestRequest) -> dict:
    """
    Run a backtest for a given symbol and strategy.

    Returns backtest summary metrics.
    Live trading is permanently disabled.
    """
    from backtesting.engine import BacktestEngine
    from broker.mock import MockBroker
    from strategies.ema_crossover import EMACrossoverStrategy
    from strategies.rsi_mean_reversion import RSIMeanReversionStrategy
    from strategies.base import AbstractStrategy

    if request.ticker not in NIFTY100_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"{request.ticker} is not in the Nifty 100 universe.",
        )

    # Build strategy
    strategy: AbstractStrategy
    if request.strategy == "ema_crossover":
        strategy = EMACrossoverStrategy(
            fast_period=request.fast_period,
            slow_period=request.slow_period,
        )
    elif request.strategy == "rsi_mean_reversion":
        strategy = RSIMeanReversionStrategy()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {request.strategy}")

    # Generate synthetic candles for demo (replace with DB query in production)
    broker = MockBroker()
    candles = broker.generate_candles(
        ticker=request.ticker,
        count=300,
        base_price=Decimal("1000"),
    )

    import pandas as pd
    df = pd.DataFrame([
        {"timestamp": c.timestamp, "open": float(c.open), "high": float(c.high),
         "low": float(c.low), "close": float(c.close), "volume": c.volume}
        for c in candles
    ])

    engine = BacktestEngine(
        strategy=strategy,
        capital=Decimal(str(request.initial_capital)),
    )
    report = engine.run(ticker=request.ticker, candles_df=df)

    return {
        "message": "Backtest completed",
        "mode": "backtest",
        "live_trading": False,
        **report.to_dict(),
    }


@app.get("/api/v1/portfolio", tags=["Portfolio"])
async def get_portfolio() -> dict:
    """Return current paper portfolio snapshot (empty at startup)."""
    return {
        "mode": "paper",
        "cash": 10000.0,
        "positions": [],
        "total_equity": 10000.0,
        "realised_pnl": 0.0,
        "note": "Connect portfolio manager to get live paper state.",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)