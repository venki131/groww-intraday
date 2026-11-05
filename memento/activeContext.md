# Active Context

## Current Branch
`feature/nifty100-market-data-collection` — PR open against `main`

## Most Recent Work (this session)
Completed and pushed the **Nifty 100 market-data collection module**:

### Commits on feature branch
| SHA | Message |
|-----|---------|
| `582be53` | feat: Nifty 100 market-data collection module (all source + tests) |
| `4f5bceb` | docs: add MARKET_DATA.md |

### All 166 tests pass
- 102 original tests (unchanged)
- 64 new tests in `tests/test_data.py`

## Files Changed This Session

### New
- `database/models_market.py` — 4 ORM models: `Instrument`, `IndexMembership`, `Candle5m`, `DataDownloadJob`
- `app/market/instruments.py` — `InstrumentRegistry` with 100 Nifty 100 stocks, ISINs, Groww symbols, sector, historical membership 2010–2024
- `app/market/candles.py` — full data-quality pipeline + `CandleStore` + `CandleDownloader`
- `migrations/versions/0002_market_data_schema.py` — Alembic migration for 4 tables
- `tests/test_data.py` — 64 pure unit tests
- `docs/MARKET_DATA.md` — schema, setup, quality pipeline, anti-survivorship-bias guide

### Modified
- `app/market/historical_data.py` — added `normalize_to_utc()` + `detect_gaps()` wrappers
- `broker/mock.py` — live-mode guard at `__init__` (re-applied from fix branch; not yet merged to main)
- `strategies/ema_crossover.py` — symmetric EMA crossover `prev_fast <= prev_slow` (same)

## Next Steps
1. **Merge PR** `feature/nifty100-market-data-collection` → `main`
2. **Re-merge** `fix/live-trading-guard-and-ema-crossover` if still open (or confirm it's already in main)
3. **Next feature**: backtesting engine — replay historical candles through strategy, produce P&L report
4. **Future**: live order execution integration (Groww WebSocket feed → signal → place_order)

## Active Decisions
- All timestamps stored in UTC; IST 09:15 = UTC 03:45
- Zero-volume candles are **non-fatal warnings** (flag only, not filtered out)
- 30-day API chunk limit enforced in `CandleDownloader`
- Anti-survivorship bias handled via `IndexMembership.members_as_of(date)`