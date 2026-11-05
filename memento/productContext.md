# Product Context: groww-intraday

## Why This Project Exists
Retail algorithmic trading on Indian exchanges (NSE) requires reliable data pipelines, broker API integrations, and risk guardrails that most off-the-shelf tools don't provide for Groww. This project fills that gap by wrapping the Groww API with a full intraday trading framework.

## Problems It Solves
1. **Data chunking**: Groww's historical API caps responses at 60 days per request; this system transparently splits requests into chunks and merges results.
2. **Strategy automation**: Removes emotion from trading by executing pre-defined signal-based strategies.
3. **Risk enforcement**: Hard stops on per-trade loss and daily drawdown before orders reach the broker.
4. **Backtesting parity**: The same strategy code runs in backtest and live mode, ensuring no look-ahead bias drift.
5. **Observability**: Dashboard + notifications give real-time visibility without manual log tailing.

## How It Should Work
1. At market open (09:15 IST), the scheduler wakes strategies.
2. Each strategy fetches candles (via `fetch_candles_chunked`), computes indicators, and emits signals.
3. The `RiskManager` validates signals against position limits and daily P&L.
4. Approved orders are routed through `GrowwClient` (paper or live mode).
5. Fills update portfolio state; P&L is persisted to SQLite/Postgres via SQLAlchemy.
6. At 15:30 IST, all open MIS positions are squared off automatically.
7. EOD report is generated and optionally pushed via Telegram.

## User Experience Goals
- **Zero manual intervention** during market hours (except emergency kill-switch).
- **Transparent audit trail**: every decision logged with timestamp, signal values, and risk check outcome.
- **Safe by default**: live trading requires explicit opt-in; paper-trading is the default.
- **Portable**: runs locally (venv) or in Docker with the same config.