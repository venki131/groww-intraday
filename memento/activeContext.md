# Active Context: groww-intraday

## Current Status
**All foundational work + 2 bug fixes complete.** 102/102 tests pass. Two PRs open awaiting merge.

## Open PRs
| PR | Branch | Status | Contents |
|----|--------|--------|----------|
| [#1](https://github.com/venki131/groww-intraday/pull/1) | `docs/memento-and-workflow-rules` | Open | Memento, CLAUDE.md, .gitignore, GRAPH_REPORT.md |
| [#2](https://github.com/venki131/groww-intraday/pull/2) | `fix/live-trading-guard-and-ema-crossover` | Open | 2 bug fixes — 102 tests green |

## Last Completed Work
### Session 2 (bug fixes)
1. ✅ Fixed `test_live_trading_blocked` — added `LiveTradingBlockedError` guard in [`MockBroker.__init__`](../broker/mock.py) when `mode="live"`
2. ✅ Fixed `test_ema_bullish_crossover_produces_buy` — changed bullish crossover from strict `<` to `<=` in [`EMACrossoverStrategy`](../strategies/ema_crossover.py) (symmetric with bearish `>=`); catches equal→above EMA transitions
3. ✅ All 102 tests pass on branch `fix/live-trading-guard-and-ema-crossover`
4. ✅ PR #2 created and pushed to GitHub

### Session 1 (foundation)
1. ✅ Fixed chunking bug in `fetch_candles_chunked`
2. ✅ Initial GitHub push + Graphify knowledge graph (951 nodes, 1,747 edges)
3. ✅ Memento files initialized, CLAUDE.md Git workflow rules added

## Active Decisions
- **Live trading disabled**: `_LIVE_TRADING_ENABLED = False` — paper-trading validation must be completed first
- **Community labels**: Graphify communities are unnamed (`Community N`) — needs `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY`
- **pandas-ta**: currently pinned to git URL; switch to `ta` package for portability

## Next Steps (Priority Order)
1. **Merge PR #2** (bug fixes) → `main` at https://github.com/venki131/groww-intraday/pull/2
2. **Merge PR #1** (docs/memento) → `main` at https://github.com/venki131/groww-intraday/pull/1
3. **Paper-trading validation** — run system in paper mode; validate signal → order → fill cycle
4. **Fix pandas-ta dependency** — switch from git URL to `ta` package
5. **Optionally name communities** — set `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY` and re-run `graphify cluster-only .`

## Key Files to Know
- [`broker/mock.py`](../broker/mock.py) — in-memory test broker (recently fixed: live-mode guard)
- [`strategies/ema_crossover.py`](../strategies/ema_crossover.py) — EMA crossover strategy (recently fixed: symmetric crossover)
- [`app/market/historical_data.py`](../app/market/historical_data.py) — chunked candle fetch
- [`config/settings.yaml`](../config/settings.yaml) — central config
- [`graphify-out/GRAPH_REPORT.md`](../graphify-out/GRAPH_REPORT.md) — architecture summary