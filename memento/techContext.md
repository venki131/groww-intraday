# Tech Context: groww-intraday

## Language & Runtime
- **Python 3.11+** (virtual env at `trade/groww-intraday/.venv`)
- Activate: `source trade/groww-intraday/.venv/bin/activate`

## Key Dependencies
| Package | Purpose |
|---------|---------|
| `pandas` | OHLCV data manipulation |
| `pandas-ta` | Technical indicators (pinned to git URL — not on PyPI) |
| `SQLAlchemy` + `alembic` | ORM + database migrations |
| `FastAPI` + `uvicorn` | Optional REST control plane |
| `httpx` | Async HTTP client for Groww API |
| `tenacity` | Retry logic on API failures |
| `pytest` + `pytest-cov` | Test framework + coverage |
| `python-dotenv` | Env var loading |
| `pyyaml` | YAML config parsing |

> ⚠️ `pandas-ta` is installed from a git URL in `requirements.txt` — may fail on clean machines. Consider switching to the `ta` package.

## Broker API
- **Groww API** (unofficial/internal)
- Authentication: bearer token — **requires daily manual renewal**
- Token stored in `.env` as `GROWW_API_TOKEN`
- Base URL and endpoints configured in `config/settings.yaml`
- Rate limits handled via `tenacity` retries with exponential backoff

## Database
- **SQLite** (default, local dev) or **PostgreSQL** (production via `docker-compose.yml`)
- Alembic migrations in `migrations/`
- Connection config in `database/connection.py`

## Infrastructure
- `Dockerfile` + `docker-compose.yml` for containerised deployment
- `alembic.ini` for migration management

## Development Tools
- **uv** (package manager) — installed at `~/.local/bin/uv`; source with `source ~/.local/bin/env`
- **gh CLI** — installed at `/opt/homebrew/bin/gh`; authenticated as `venki131`
- **Graphify** (`graphifyy` PyPI package) — installed via `uv tool install graphifyy`
  - CLI command: `graphify`
  - Knowledge graph at `graphify-out/`
  - AiDE skill at `.claude/skills/graphify/`

## Environment Variables (`.env`)
```
GROWW_API_TOKEN=<daily renewed token>
DB_URL=sqlite:///./groww_intraday.db      # or postgres://...
TELEGRAM_BOT_TOKEN=<optional>
TELEGRAM_CHAT_ID=<optional>
LOG_LEVEL=INFO
```

## Running Tests
```bash
cd trade/groww-intraday
source .venv/bin/activate
pytest --override-ini="addopts="          # bypasses --cov-* in pytest.ini
```

## Running the System
```bash
cd trade/groww-intraday
source .venv/bin/activate
python -m app.main                         # paper trading (default)
```

## Known Constraints
- `_LIVE_TRADING_ENABLED = False` — must remain `False` until paper-trading validation is complete
- Groww API token expires daily; no programmatic renewal API available
- `pandas-ta` git dependency may break on fresh installs