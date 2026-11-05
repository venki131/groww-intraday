# Progress

## What Works ✅

### Core Trading System (on `main` @ `cbbd6be`)
- **Configuration** (`config/`) — YAML + env-var loader, logging setup
- **Database** (`database/`) — async SQLAlchemy + Alembic migrations
  - Migration `0001` — base tables: `orders`, `trades`, `positions`
- **Broker abstraction** (`broker/`) — `BrokerBase` interface, `GrowwBroker` live impl, `MockBroker` paper-trading
  - `MockBroker` raises `LiveTradingBlockedError` at `__init__` when `mode="live"` ✅ (included in feature branch)
- **Strategies** (`strategies/`) — `StrategyBase`, `EmaCrossoverStrategy` (9/21 EMA)
  - Symmetric bullish crossover `prev_fast <= prev_slow` ✅ (included in feature branch)
- **API integration** (`app/api/`) — Groww OAuth, rate-limited HTTP client, candle + order endpoints
- **Historical data** (`app/market/historical_data.py`) — base candle-fetch helpers
- **102 tests** (`tests/`) — broker, config, DB, strategies, API — all passing

### Nifty 100 Market-Data Module (on `feature/nifty100-market-data-collection` @ `4f5bceb`)
- **`database/models_market.py`** — `Instrument`, `IndexMembership`, `Candle5m`, `DataDownloadJob` ORM models
- **`app/market/instruments.py`** — `InstrumentRegistry` with 100 Nifty 100 stocks
  - ISINs, Groww symbols, sector/industry, historical membership 2010–2024
  - `members_as_of(date)` → anti-survivorship-bias constituent lookup
- **`app/market/candles.py`** — full data-quality pipeline
  - `normalize_to_utc()` — IST→UTC conversion
  - `validate_candles()` → `DataQualityReport` with 6 `QualityFlag` types
  - `apply_quality_flags()` — adds boolean columns to DataFrame
  - `detect_missing_intervals()` — finds gaps in 75-slot NSE session
  - `CandleStore` — async upsert/fetch from `candles_5m`
  - `CandleDownloader` — 30-day chunked download orchestrator
- **`migrations/versions/0002_market_data_schema.py`** — Alembic migration (4 new tables)
- **`tests/test_data.py`** — 64 pure unit tests (no DB / network)
- **`docs/MARKET_DATA.md`** — schema, setup, quality pipeline, anti-survivorship-bias guide
- **166/166 tests pass** (102 original + 64 new)

### Infrastructure
- GitHub repo: `venki131/groww-intraday`
- Branch protection on `main` (1 approving review required)
- Memento documentation (6 core files)
- `.aiderules` / `CLAUDE.md` with Git workflow rules
- Graphify knowledge graph (`graphify-out/GRAPH_REPORT.md`)

---

## What's Left 🔲

### Immediate
- [ ] Merge PR `feature/nifty100-market-data-collection` → `main`
- [ ] Confirm `fix/live-trading-guard-and-ema-crossover` is merged or superseded

### Next Feature: Backtesting Engine
- [ ] `app/backtest/engine.py` — replay `Candle5m` rows through a `StrategyBase`, emit trades
- [ ] `app/backtest/metrics.py` — Sharpe ratio, max drawdown, win rate, CAGR
- [ ] `app/backtest/report.py` — console + CSV output
- [ ] `tests/test_backtest.py` — deterministic fixture-based tests

### Future
- [ ] Live order execution integration (Groww WebSocket → signal → `place_order`)
- [ ] Portfolio-level position sizing (Kelly / fixed-fraction)
- [ ] Scheduled data refresh (cron / APScheduler) for daily candle ingestion
- [ ] CI pipeline (GitHub Actions: run tests on every PR)

---

## Known Issues

| Issue | Status |
|-------|--------|
| `broker/mock.py` live-mode guard applied on feature branch but not yet in `main` | Pending PR merge |
| `strategies/ema_crossover.py` symmetric fix applied on feature branch but not yet in `main` | Pending PR merge |
| No CI pipeline yet — tests run manually | Future work |
| `CandleDownloader` requires a live Groww API token for integration tests | Integration tests not yet written |

---

## Test Count History

| Milestone | Tests |
|-----------|-------|
| Initial system | 102 |
| + Nifty 100 market-data module | **166** |