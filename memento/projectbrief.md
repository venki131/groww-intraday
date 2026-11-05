# Project Brief: groww-intraday

## Overview
A Python-based algorithmic intraday trading system built on top of the **Groww broker API**. It is designed for automated signal generation, order execution, risk management, and backtesting — all scoped to NSE intraday equities (MIS orders, session 09:15–15:30 IST).

## Core Requirements
- Fetch historical OHLCV candle data from Groww API in configurable chunks (handles 60-day API limit)
- Run technical indicator-based strategies (e.g., EMA crossover, RSI, VWAP)
- Execute paper-trading and (optionally) live orders via GrowwClient
- Risk management: per-trade stop-loss, daily drawdown cap, position sizing
- Backtesting engine with walk-forward validation
- Dashboard / reporting for P&L, drawdown, sharpe
- Notifications (Telegram/email) on trade events
- Full test suite (pytest, 60 tests passing)

## Scope Boundaries
- **Exchange**: NSE only (intraday MIS, no F&O, no BSE)
- **Live trading**: Disabled by default (`_LIVE_TRADING_ENABLED = False`); must be enabled only after paper-trading validation
- **Token management**: Groww API token requires daily manual renewal
- **Deployment**: Docker-ready (`Dockerfile`, `docker-compose.yml`)

## GitHub Repository
- URL: https://github.com/venki131/groww-intraday
- Branch: `main`
- Visibility: Public