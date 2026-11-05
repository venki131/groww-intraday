# System Patterns: groww-intraday

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Scheduler / Main Loop              │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │      Strategy Layer      │
          │  (EMA, RSI, VWAP, etc.)  │
          └────────────┬────────────┘
                       │ signals
          ┌────────────▼────────────┐
          │      Risk Manager        │
          │  (SL, drawdown, sizing)  │
          └────────────┬────────────┘
                       │ approved orders
          ┌────────────▼────────────┐
          │      GrowwClient         │
          │  (Broker API wrapper)    │
          └────────────┬────────────┘
                       │ fills
     ┌─────────────────▼─────────────────┐
     │  Portfolio / Database / Reporting  │
     └────────────────────────────────────┘
```

## Key Modules

| Directory | Responsibility |
|-----------|---------------|
| `app/market/` | Historical candle fetch (`fetch_candles_chunked`), live quote streaming |
| `broker/` | `GrowwClient` — API auth, order placement, order book |
| `strategies/` | Base class + concrete strategy implementations |
| `risk/` | `RiskManager` — position limits, stop-loss enforcement, daily P&L cap |
| `portfolio/` | Portfolio state, holdings, cash tracking |
| `backtesting/` | Walk-forward engine using the same strategy interface |
| `database/` | SQLAlchemy models, Alembic migrations |
| `api/` | FastAPI REST endpoints (optional live control plane) |
| `dashboard/` | Lightweight HTML/JS dashboard fed by the API |
| `notifications/` | Telegram / email adapters |
| `reporting/` | EOD report generation (P&L, drawdown, sharpe) |
| `config/` | YAML-based config (`settings.yaml`) + env override via `ConfigManager` |

## Critical Design Patterns

### 1. Chunked Historical Data Fetch
- Groww API limit: 60 days per request
- Fix: normalize `start_dt`/`end_dt` to midnight before `_date_chunks`, then re-apply session times (09:15/15:30) per chunk via `max()`/`min()` clamping
- Same-date guard: if `_chunk_end_norm <= _chunk_start_norm`, add `+1 second` to avoid empty range
- File: [`app/market/historical_data.py`](../app/market/historical_data.py)

### 2. Strategy Interface
- All strategies inherit a common base class with `generate_signals(candles: pd.DataFrame) -> Signal`
- Strategy code is shared between live and backtest engine (no duplication)

### 3. Risk-First Order Flow
- No order bypasses `RiskManager`; it is the single gateway between signal and execution
- Paper mode and live mode use the same `RiskManager` path

### 4. Config Hierarchy
- `config/settings.yaml` → base defaults
- Environment variables → override at runtime
- `ConfigManager` resolves the merged view

### 5. Knowledge Graph (Graphify)
- `graphify-out/graph.json`: 951 nodes, 1,747 edges, 53 communities from 51 Python files
- `graphify-out/GRAPH_REPORT.md`: architecture summary, god nodes, community map
- `graphify-out/graph.html`: interactive force-directed visualization
- `.claude/skills/graphify/`: AiDE skill for `/graphify` queries during development
- Regenerate: `source ~/.local/bin/env && graphify extract . --code-only`

## Testing Pattern
- Framework: `pytest` with `pytest-cov`
- Run: `cd trade/groww-intraday && source .venv/bin/activate && pytest --override-ini="addopts="`
- 60 tests, all passing
- Coverage config in `pytest.ini` (requires `--override-ini="addopts="` to skip `--cov-*` when running without coverage)