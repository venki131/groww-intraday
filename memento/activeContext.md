# Active Context: groww-intraday

## Current Status
**All foundational work is complete.** The project is fully committed and pushed to GitHub. The knowledge graph has been generated and pushed. The memento files are being initialized in this session.

## Last Completed Work (this session)
1. ✅ Installed missing Python deps (`tenacity`, `pytest-cov`, `httpx`, etc.) into `.venv`
2. ✅ Fixed `pytest.ini` addopts conflict — solved with `--override-ini="addopts="`
3. ✅ Fixed chunking bug in [`fetch_candles_chunked`](../app/market/historical_data.py) — normalize to midnight before `_date_chunks`, re-apply session times per chunk, same-date `+1 second` guard
4. ✅ All 60 tests pass (`60 passed in 0.32s`)
5. ✅ Initial GitHub push — `https://github.com/venki131/groww-intraday` (58 files, 8,088 insertions)
6. ✅ Installed Graphify (`uv tool install graphifyy`)
7. ✅ Generated knowledge graph — 951 nodes, 1,747 edges, 53 communities from 51 Python files
8. ✅ Pushed Graphify outputs to GitHub (`cbbd6be..efc9e51  main -> main`)
9. ✅ Initialized memento files

## Active Decisions
- **Live trading disabled**: `_LIVE_TRADING_ENABLED = False` — paper-trading validation must be completed first
- **Community labels**: Graphify communities are unnamed (`Community N` placeholders) — no LLM API key configured; can be named by setting `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY` and re-running `graphify cluster-only .`
- **pandas-ta**: currently pinned to git URL in `requirements.txt`; consider switching to `ta` package for clean-install reliability

## Next Steps (Priority Order)
1. **Explore the knowledge graph** — open `graphify-out/graph.html` in browser:
   ```bash
   open trade/groww-intraday/graphify-out/graph.html
   ```
2. **Run graph queries** to understand architecture:
   ```bash
   source ~/.local/bin/env
   cd trade/groww-intraday
   graphify query "what connects the broker to the strategy layer?"
   graphify path "GrowwClient" "fetch_candles_chunked"
   graphify explain "RiskManager"
   ```
3. **Paper-trading validation** — run the system in paper mode and validate signal → order → fill cycle
4. **Optionally name communities** — set `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY` and re-run `graphify cluster-only .`
5. **Fix pandas-ta dependency** — switch from git URL to `ta` package for portability

## Key Files to Know
- [`app/market/historical_data.py`](../app/market/historical_data.py) — chunked candle fetch (recently fixed)
- [`config/settings.yaml`](../config/settings.yaml) — central config
- [`graphify-out/GRAPH_REPORT.md`](../graphify-out/GRAPH_REPORT.md) — architecture summary from knowledge graph
- [`graphify-out/graph.html`](../graphify-out/graph.html) — interactive visualization