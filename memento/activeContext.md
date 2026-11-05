# Active Context: groww-intraday

## Current Status
**Interactive dashboard complete.** PR #4 open for review. 166/166 tests still green.

## Open PRs
| PR | Branch | Status | Contents |
|----|--------|--------|----------|
| [#4](https://github.com/venki131/groww-intraday/pull/4) | `feature/interactive-dashboard` | Open | 4-tab Streamlit dashboard rewrite |
| [#3](https://github.com/venki131/groww-intraday/pull/3) | `feature/nifty100-market-data-collection` | Open | Nifty 100 market-data collection module |

## Last Completed Work
### Session 4 — Interactive Dashboard
1. ✅ Rewrote [`dashboard/app.py`](../dashboard/app.py) (152 → ~660 lines) with 4 interactive tabs
2. ✅ **Tab 1 — Chart & Signals**: Plotly candlestick + EMA overlays + buy/sell markers + volume subplot
3. ✅ **Tab 2 — Backtest**: Full `BacktestEngine` integration, 8 KPIs, equity curve, trade log, P&L histogram
4. ✅ **Tab 3 — Paper Trading**: Session-persistent `MockBroker`, BUY/SELL order entry, positions table, order history, reset
5. ✅ **Tab 4 — Universe Browser**: 100-stock table with sector filter + text search + sector donut chart
6. ✅ Branch `feature/interactive-dashboard` pushed, PR #4 created

### Session 3 — Nifty 100 Market-Data Collection
1. ✅ 4 new ORM models (`Instrument`, `IndexMembership`, `Candle5m`, `DataDownloadJob`)
2. ✅ `InstrumentRegistry` with 100 stocks, ISINs, sectors, Groww symbols, historical membership
3. ✅ Data quality pipeline + 64 new tests → 166/166 total passing
4. ✅ PR #3 open

### Sessions 1–2 — Foundation + Bug Fixes (merged)
- PRs #1 and #2 merged into `main` (`d420429`)
- `MockBroker` live-mode guard, symmetric EMA crossover, Memento, CLAUDE.md, Graphify

## Active Decisions
- **Live trading disabled**: `_LIVE_TRADING_ENABLED = False` — paper-trading validation must complete first
- **Dashboard uses synthetic data**: `MockBroker.generate_candles()` only — no live network calls
- **InstrumentRegistry import in Tab 4**: wrapped in `try/except` — degrades gracefully to plain symbol list
- **Paper trading state**: persisted across tab switches via `st.session_state`
- **pandas-ta**: currently pinned to git URL; switch to `ta` package for portability

## Next Steps (Priority Order)
1. **Merge PR #4** (interactive dashboard) → `main`
2. **Merge PR #3** (market-data collection) → `main`
3. **Paper-trading validation** — run system in paper mode; validate signal → order → fill cycle end-to-end
4. **Fix pandas-ta dependency** — switch from git URL to `ta` package
5. **Multi-symbol backtest comparison** — run same strategy across multiple tickers, compare KPIs in Tab 2
6. **Live data feed** — Groww WebSocket integration when paper-trading phase is complete

## Key Files to Know
- [`dashboard/app.py`](../dashboard/app.py) — 4-tab interactive Streamlit UI (recently rewritten)
- [`broker/mock.py`](../broker/mock.py) — in-memory paper broker with `generate_candles()`
- [`strategies/ema_crossover.py`](../strategies/ema_crossover.py) — EMA crossover strategy
- [`backtesting/engine.py`](../backtesting/engine.py) — `BacktestEngine`, `BacktestReport`
- [`app/market/instruments.py`](../app/market/instruments.py) — `InstrumentRegistry` (100 stocks)
- [`market/universe.py`](../market/universe.py) — `NIFTY100_SYMBOLS` list
- [`config/settings.yaml`](../config/settings.yaml) — central config