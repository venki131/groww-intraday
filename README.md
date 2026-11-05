# Groww Intraday Automation

> **Mode: BACKTEST and PAPER only — Live trading is permanently disabled.**

A modular Python 3.11+ algorithmic trading system for NSE Nifty 100 intraday equities using the Groww Trading API.

---

## ⚠️ Safety Notice

- **Live order placement is permanently blocked** at the code level.
- Credentials are loaded exclusively from environment variables — never hardcoded.
- All strategies are tested against MockBroker; no network calls required.

---

## Architecture

```
groww-intraday/
├── api/              FastAPI REST backend
├── backtesting/      Event-driven backtest engine
├── broker/           Abstract broker + Groww + MockBroker
├── config/           Settings management + structured logging
├── dashboard/        Streamlit UI
├── database/         SQLAlchemy models + Alembic migrations
├── market/           Nifty 100 universe + trading hours
├── migrations/       Alembic migration scripts
├── notifications/    Telegram alerts
├── portfolio/        Portfolio state tracker
├── reporting/        CSV/DataFrame report generator
├── risk/             Pre-trade risk manager
├── strategies/       Abstract strategy + EMA crossover + RSI
└── tests/            Pytest test suite
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Docker (optional but recommended)

### 2. Environment Setup

```bash
cd trade/groww-intraday
cp .env.example .env
# Edit .env with your credentials (DB password, Telegram token, etc.)
```

### 3. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Database Setup

```bash
# Start PostgreSQL (or use Docker)
docker run -d --name groww_pg \
  -e POSTGRES_DB=groww_intraday \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=changeme \
  -p 5432:5432 postgres:16-alpine

# Run Alembic migrations
alembic upgrade head
```

### 5. Run Tests

```bash
pytest
```

### 6. Start FastAPI Server

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/docs
```

### 7. Start Streamlit Dashboard

```bash
streamlit run dashboard/app.py
# Dashboard: http://localhost:8501
```

---

## Docker

```bash
# Start all services (Postgres + API + Dashboard)
cp .env.example .env   # edit DB_PASSWORD at minimum
docker-compose up --build

# Services:
#   API       → http://localhost:8000
#   Dashboard → http://localhost:8501
#   Postgres  → localhost:5432
```

---

## Running a Backtest via API

```bash
curl -X POST http://localhost:8000/api/v1/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "RELIANCE",
    "strategy": "ema_crossover",
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "initial_capital": 10000,
    "fast_period": 9,
    "slow_period": 21
  }'
```

---

## Configuration

All settings live in [`config/settings.yaml`](config/settings.yaml) and can be overridden via environment variables.

| Key | Default | Description |
|-----|---------|-------------|
| `INITIAL_CAPITAL` | 10000 | Starting capital (INR) |
| `MAX_RISK_PER_TRADE_PCT` | 1.0 | Max loss per trade as % of capital |
| `MAX_OPEN_POSITIONS` | 3 | Max simultaneous positions |
| `MAX_DAILY_LOSS_PCT` | 3.0 | Daily loss circuit-breaker |
| `CANDLE_INTERVAL` | 5 | Candle size in minutes |
| `EXCHANGE` | NSE | Exchange code |
| `BACKTEST_COMMISSION_PCT` | 0.03 | Brokerage commission % |
| `BACKTEST_SLIPPAGE_PCT` | 0.01 | Slippage % |
| `TELEGRAM_ENABLED` | false | Enable Telegram notifications |

---

## Strategies

| Strategy | Signal Logic |
|----------|-------------|
| `ema_crossover` | BUY when fast EMA crosses above slow EMA; SELL on reverse |
| `rsi_mean_reversion` | BUY when RSI recovers from oversold; SELL from overbought |

### Adding a New Strategy

1. Create `strategies/my_strategy.py` extending [`AbstractStrategy`](strategies/base.py)
2. Implement `generate_signals()` and `generate_all_signals()`
3. Register in `strategies/__init__.py`
4. Add to `api/main.py` strategy selector

---

## Database Schema

| Table | Description |
|-------|-------------|
| `symbols` | Nifty 100 instrument metadata |
| `candles` | 5-minute OHLCV price data |
| `orders` | Order lifecycle (paper/backtest) |
| `trades` | Executed trade records |
| `positions` | Open/closed position snapshots |
| `daily_pnl` | Per-symbol daily P&L |
| `backtest_runs` | Backtest session metadata |
| `backtest_results` | Per-trade backtest results |

---

## Testing

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_strategies.py -v

# Run broker tests only
pytest tests/test_broker.py -v
```

Tests use `MockBroker` — no real API calls, no network required.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check (API + DB) |
| `GET` | `/api/v1/universe` | Nifty 100 symbols |
| `GET` | `/api/v1/market/status` | NSE open/closed |
| `POST` | `/api/v1/backtest` | Run backtest |
| `GET` | `/api/v1/portfolio` | Paper portfolio snapshot |

Interactive docs: `http://localhost:8000/docs`

---

## Project Rules

This project uses **Ponytail (Lazy Senior Dev)** mode — see [`.clinerules`](.clinerules).

- Minimum code that works
- No abstraction nobody asked for
- Every non-trivial change has a test
- Risk checks run before every order

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Backend | FastAPI + Uvicorn |
| Dashboard | Streamlit + Plotly |
| Database | PostgreSQL + SQLAlchemy 2.x |
| Migrations | Alembic |
| Testing | Pytest + pytest-asyncio |
| Logging | Loguru (structured JSON) |
| Containers | Docker + Docker Compose |
| Notifications | Telegram Bot API |

---

## License

For personal educational and research use only.
**Not financial advice. Never use with real money without thorough validation.**