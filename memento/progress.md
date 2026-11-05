# Progress: groww-intraday

## What Works ✅

### Core Infrastructure
- [x] Project structure with all module directories (`app/`, `broker/`, `strategies/`, `risk/`, `portfolio/`, `backtesting/`, `database/`, `api/`, `dashboard/`, `notifications/`, `reporting/`, `config/`)
- [x] YAML-based config system (`config/settings.yaml` + `ConfigManager`)
- [x] SQLAlchemy ORM + Alembic migrations
- [x] Docker support (`Dockerfile`, `docker-compose.yml`)
- [x] Logging configuration

### Data Pipeline
- [x] `fetch_candles_chunked` — transparent 60-day chunking for Groww API
- [x] Chunking bug fixed: midnight normalization + per-chunk session time clamping + same-date guard
- [x] Historical OHLCV data fetch working correctly for any date range

### Testing
- [x] 60 tests, all passing
- [x] `pytest-cov` installed; coverage reporting available
- [x] Known workaround: `pytest --override-ini="addopts="` to skip `--cov-*` when not measuring coverage

### DevOps / Tooling
- [x] GitHub repository: https://github.com/venki131/groww-intraday (public, `main` branch)
- [x] `.gitignore` configured (excludes `.venv/`, `.env`, `__pycache__/`, `*.log`)
- [x] `gh` CLI authenticated as `venki131`
- [x] Graphify knowledge graph generated and committed:
  - 951 nodes, 1,747 edges, 53 communities from 51 Python files
  - Interactive visualization at `graphify-out/graph.html`
  - Architecture report at `graphify-out/GRAPH_REPORT.md`
  - AiDE skill at `.claude/skills/graphify/`
- [x] Memento documentation initialized

## What's Left to Build 🔲

### Paper Trading Validation
- [ ] End-to-end paper trade cycle: signal → risk check → order → fill → portfolio update
- [ ] Scheduled market-open/close hooks
- [ ] Auto square-off at 15:30 IST

### Live Trading (blocked on paper-trading validation)
- [ ] Set `_LIVE_TRADING_ENABLED = True` after validation
- [ ] Groww API token auto-refresh mechanism (currently manual daily renewal)

### Strategies
- [ ] Validate EMA crossover strategy in paper mode
- [ ] Validate RSI strategy
- [ ] Validate VWAP strategy

### Notifications
- [ ] Telegram bot integration end-to-end test
- [ ] Email notification adapter

### Dashboard
- [ ] Confirm FastAPI + dashboard serving works end-to-end

### Dependency
- [ ] Replace `pandas-ta` git URL with `ta` package for clean-install portability

### Knowledge Graph Enhancement
- [ ] Set `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY` and re-run `graphify cluster-only .` for named community labels (currently `Community N` placeholders)

## Known Issues / Risks

| Issue | Severity | Notes |
|-------|----------|-------|
| Groww API token manual daily renewal | High | No programmatic refresh available |
| `pandas-ta` git URL dependency | Medium | May fail on fresh machines; switch to `ta` |
| `_LIVE_TRADING_ENABLED = False` | Intentional | Safety guard; never enable without paper-trading validation |
| Graphify community names are `Community N` | Low | Needs LLM API key to generate meaningful names |

## Current Commit History (GitHub)
| Commit | Description |
|--------|-------------|
| `efc9e51` | feat: add Graphify knowledge graph (951 nodes, 1747 edges, 53 communities) |
| `cbbd6be` | Initial commit — 58 files, 8,088 insertions |