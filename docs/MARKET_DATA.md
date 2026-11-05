# Market Data Module

Documentation for the Nifty 100 historical candle-data collection pipeline.

---

## Table of Contents

1. [Overview](#overview)
2. [Database Schema](#database-schema)
3. [Setup](#setup)
4. [InstrumentRegistry](#instrumentregistry)
5. [Data Quality Pipeline](#data-quality-pipeline)
6. [Downloading Historical Candles](#downloading-historical-candles)
7. [Anti-Survivorship-Bias Backtesting](#anti-survivorship-bias-backtesting)
8. [Updating the Nifty 100 Constituent List](#updating-the-nifty-100-constituent-list)

---

## Overview

This module downloads, validates, and stores 5-minute OHLCV candles for the
100 stocks that constitute the **Nifty 100 index** from the Groww API.

```
app/market/
├── instruments.py      ← InstrumentRegistry (100 stocks, ISINs, Groww symbols, membership history)
├── candles.py          ← DataQualityReport, validate_candles(), CandleStore, CandleDownloader
└── historical_data.py  ← normalize_to_utc(), detect_gaps() (re-exports from candles.py)

database/
└── models_market.py    ← Instrument, IndexMembership, Candle5m, DataDownloadJob ORM models

migrations/versions/
└── 0002_market_data_schema.py  ← Alembic migration

tests/
└── test_data.py        ← 64 pure unit tests (no DB / network required)
```

---

## Database Schema

### `instruments`
Stores one row per tradeable instrument.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `ticker` | String(20) | NSE symbol, e.g. `RELIANCE` — **unique** |
| `isin` | String(12) | e.g. `INE002A01018` |
| `groww_symbol` | String(30) | e.g. `NSE-RELIANCE` |
| `name` | String(100) | Full company name |
| `sector` | String(60) | e.g. `Energy` |
| `industry` | String(60) | e.g. `Oil & Gas` |
| `is_active` | Boolean | Currently listed |
| `created_at` | DateTime | UTC |

### `index_membership`
Historical snapshots of which stocks were in which index on which dates.
Used to avoid **survivorship bias** in backtests.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `index_name` | String(50) | e.g. `NIFTY100` |
| `ticker` | String(20) | FK → `instruments.ticker` |
| `effective_from` | Date | First date the stock was in the index |
| `effective_to` | Date \| NULL | Last date, or NULL if still current |

Unique constraint: `(index_name, ticker, effective_from)`.

### `candles_5m`
One row per instrument per 5-minute slot.

| Column | Type | Notes |
|--------|------|-------|
| `ticker` | String(20) | PK part 1 |
| `timestamp_utc` | DateTime | PK part 2 — always UTC; IST 09:15 = UTC 03:45 |
| `open` | Numeric(12,4) | |
| `high` | Numeric(12,4) | |
| `low` | Numeric(12,4) | |
| `close` | Numeric(12,4) | |
| `volume` | BigInteger | |
| `is_zero_volume` | Boolean | Non-fatal quality warning |
| `is_interpolated` | Boolean | True when gap-filled by upstream API |
| `has_ohlc_error` | Boolean | True when high < low or close outside [low, high] |
| `source` | String(20) | `groww_api`, `manual`, etc. |
| `ingested_at` | DateTime | UTC insert time |

PK: `(ticker, timestamp_utc)`.  
Partial index on `is_zero_volume = true` for fast quality queries.

### `data_download_jobs`
Tracks each download run.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `ticker` | String(20) | |
| `from_date` | Date | Requested start |
| `to_date` | Date | Requested end |
| `status` | String(20) | `pending`, `running`, `done`, `failed` |
| `candles_fetched` | Integer | Candles received from API |
| `candles_stored` | Integer | Candles written to DB |
| `quality_issues` | Integer | Issues found by validator |
| `error_message` | Text | NULL unless `status = failed` |
| `started_at` / `finished_at` | DateTime | UTC |

---

## Setup

### 1. Run the Alembic migration

```bash
cd trade/groww-intraday
.venv/bin/python -m alembic upgrade head
```

This creates all four tables (`instruments`, `index_membership`, `candles_5m`,
`data_download_jobs`).

### 2. Seed instrument data

```python
from database.connection import get_session
from app.market.instruments import get_registry

async def seed():
    async with get_session() as session:
        registry = get_registry()
        await registry.db_seed(session)   # upserts 100 rows into instruments + index_membership

import asyncio
asyncio.run(seed())
```

Or from the CLI once a convenience script exists:

```bash
.venv/bin/python -m app.market.instruments seed
```

### 3. Download candles

```python
from database.connection import get_session
from app.market.candles import CandleDownloader
from app.market.instruments import get_registry

async def download():
    registry = get_registry()
    tickers = registry.members_as_of("today")          # all 100 current stocks

    async with get_session() as session:
        downloader = CandleDownloader(session)
        for ticker in tickers:
            report = await downloader.download(
                ticker=ticker,
                from_date="2024-01-01",
                to_date="2024-12-31",
            )
            print(report.summary())

import asyncio
asyncio.run(download())
```

The downloader automatically splits the date range into **≤30 calendar-day
chunks** (Groww API limit) and writes each chunk to `candles_5m` via upsert.

---

## InstrumentRegistry

```python
from app.market.instruments import get_registry

reg = get_registry()          # module-level singleton, instantiated once

# Basic lookups
reg.groww_symbol("RELIANCE")  # → "NSE-RELIANCE"
reg.isin("TCS")               # → "INE467B01029"

# Filter by sector
reg.by_sector("Pharma")       # → List[InstrumentRecord]
reg.sectors()                 # → sorted list of unique sector names

# Anti-survivorship bias
reg.members_as_of("2022-01-01")  # → List[str] — tickers IN the index on that date
reg.members_as_of("today")       # → all 100 current tickers

# Seed to database (async)
async with get_session() as session:
    await reg.db_seed(session)
```

The `members_as_of()` method queries `IndexMembership` entries where
`effective_from <= date < effective_to` (or `effective_to IS NULL` for
current members).

---

## Data Quality Pipeline

Every downloaded DataFrame passes through a quality pipeline in `app/market/candles.py`:

### Step 1 — UTC normalization

```python
from app.market.candles import normalize_to_utc

df = normalize_to_utc(df)
# Renames 'timestamp' → 'timestamp_utc'
# Converts IST-naive datetimes to UTC-aware
# IST 09:15 becomes UTC 03:45
```

### Step 2 — Validate candles

```python
from app.market.candles import validate_candles

report = validate_candles(df, ticker="RELIANCE")
print(report.summary())
# DataQualityReport(ticker='RELIANCE', total=75, issues=1, is_clean=False)

for issue in report.issues:
    print(issue.flag, issue.timestamp_utc, issue.detail)
```

**Quality flags** (`QualityFlag` enum):

| Flag | Severity | Meaning |
|------|----------|---------|
| `ZERO_VOLUME` | Warning (non-fatal) | Volume == 0 (holiday/halt) |
| `OHLC_ERROR` | Error | `high < low` or `close` outside `[low, high]` |
| `NEGATIVE_PRICE` | Error | Any OHLC value ≤ 0 |
| `MISSING_INTERVAL` | Warning | Expected 5-min slot absent from data |
| `DUPLICATE_TIMESTAMP` | Error | Same `timestamp_utc` appears twice |
| `OUT_OF_SESSION` | Warning | Candle outside 09:15–15:30 IST |

A `DataQualityReport.is_clean` is `True` only when there are **zero errors**;
warnings (zero-volume, missing interval, out-of-session) do not mark a report
as dirty.

### Step 3 — Apply quality flags

```python
from app.market.candles import apply_quality_flags

df = apply_quality_flags(df)
# Adds boolean columns: is_zero_volume, has_ohlc_error, is_interpolated
```

### Step 4 — Detect missing intervals

```python
from app.market.candles import detect_missing_intervals
import pandas as pd

trading_dates = pd.bdate_range("2024-01-01", "2024-01-31")
missing = detect_missing_intervals(df, trading_dates)
# → sorted List[datetime] of UTC timestamps that should exist but don't
```

A full NSE session has **75 five-minute slots** per trading day
(09:15–15:30 IST = 03:45–10:00 UTC).

---

## Downloading Historical Candles

### CandleStore — low-level DB access

```python
from app.market.candles import CandleStore

store = CandleStore(session)

# Upsert a DataFrame of candles
await store.upsert(df, ticker="RELIANCE")

# Fetch candles for a date range
df = await store.fetch("RELIANCE", from_date="2024-01-01", to_date="2024-01-31")
```

### CandleDownloader — high-level orchestrator

```python
from app.market.candles import CandleDownloader

downloader = CandleDownloader(session)

report = await downloader.download(
    ticker="RELIANCE",
    from_date="2023-01-01",
    to_date="2024-12-31",    # spans >30 days → auto-chunked
)
# report: DataQualityReport with aggregated counts
```

Under the hood, `CandleDownloader`:
1. Splits the range into 30-day chunks
2. Calls the Groww API for each chunk
3. Runs `normalize_to_utc()` → `validate_candles()` → `apply_quality_flags()`
4. Logs any quality issues
5. Upserts clean candles to `candles_5m`
6. Creates a `DataDownloadJob` row for audit

---

## Anti-Survivorship-Bias Backtesting

A common backtesting mistake is using the **current** index constituents to
test strategies on **historical** data. This inflates performance because
survivors (stocks still in the index) tend to be the best performers.

This module prevents it via `IndexMembership`:

```python
from app.market.instruments import get_registry

reg = get_registry()

# Get the exact 52 stocks that were in Nifty 100 on 2022-01-01
tickers_2022 = reg.members_as_of("2022-01-01")

# Backtest only on those 52 stocks for 2022 data
for ticker in tickers_2022:
    df = await store.fetch(ticker, "2022-01-01", "2022-12-31")
    run_backtest(df, ticker)
```

The `IndexMembership` table captures known constituent changes from 2010 to
2024. Each row has an `effective_from` date and an `effective_to` date (NULL
means "still a member"). When you call `members_as_of("2022-01-01")`, it
returns only rows where `effective_from <= 2022-01-01` and
`(effective_to IS NULL OR effective_to > 2022-01-01)`.

---

## Updating the Nifty 100 Constituent List

The constituent list is sourced from NSE's public index methodology page and
encoded in `app/market/instruments.py` as a list of `InstrumentRecord`
dataclasses plus an `IndexMembership`-equivalent dict for historical changes.

When NSE announces a constituent change:

1. **Add the new stock** to `NIFTY100_INSTRUMENTS` in
   [`app/market/instruments.py`](../app/market/instruments.py):

   ```python
   InstrumentRecord(
       ticker="NEWSTOCK",
       isin="INExxxxxxx",
       groww_symbol="NSE-NEWSTOCK",
       name="New Stock Ltd",
       sector="Financials",
       industry="Banking",
   ),
   ```

2. **Update membership history** — add an `effective_from` entry for the new
   stock and an `effective_to` date for the stock it replaced, in the
   `_MEMBERSHIP_OVERRIDES` dict (or equivalent structure).

3. **Verify the count** still equals 100 — the assert at import time will
   catch any off-by-one errors:

   ```python
   assert len(NIFTY100_INSTRUMENTS) == 100
   ```

4. **Re-run the seed** to update the DB:

   ```bash
   .venv/bin/python -m app.market.instruments seed
   ```

5. **Download candles** for the new stock from its `effective_from` date.

---

*Last updated: 2026-05-11*