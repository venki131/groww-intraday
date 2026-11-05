# Graph Report - groww-intraday  (2026-11-05)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 951 nodes · 1747 edges · 53 communities (34 shown, 19 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 198 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `cbbd6be3`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- models.py
- api
- main.py
- BacktestReport
- config/manager.py
- RiskManager
- fetch_candles_chunked
- MockBroker
- LiveDataFeed
- GrowwBroker
- engine.py
- logging_config.py
- broker/base.py
- test_strategies.py
- TokenCache
- GrowwClient
- test_groww_client.py
- PortfolioManager
- EMACrossoverStrategy
- _with_retry
- AbstractBroker
- RSIMeanReversionStrategy
- TestGrowwClientOrders
- TelegramNotifier
- connection.py
- Candle
- test_backtest.py
- authentication.py
- LiveTradingBlockedError
- settings.yaml
- params
- broker
- conftest.py
- .get_ltp
- Position
- market
- risk
- .get_positions
- AccountInfo
- .get_instrument
- application
- api
- backtest
- database
- logging
- trading

## God Nodes (most connected - your core abstractions)
1. `MockBroker` - 52 edges
2. `GrowwClient` - 33 edges
3. `RiskManager` - 28 edges
4. `EMACrossoverStrategy` - 27 edges
5. `GrowwBroker` - 27 edges
6. `BacktestReport` - 25 edges
7. `Signal` - 22 edges
8. `RSIMeanReversionStrategy` - 21 edges
9. `SignalType` - 20 edges
10. `AbstractStrategy` - 19 edges

## Surprising Connections (you probably didn't know these)
- `run_backtest()` --uses--> `BacktestEngine`  [INFERRED]
  api/main.py → backtesting/engine.py
- `BacktestEngine` --uses--> `RiskManager`  [INFERRED]
  backtesting/engine.py → risk/manager.py
- `BacktestEngine` --uses--> `SignalType`  [INFERRED]
  backtesting/engine.py → strategies/base.py
- `run_backtest()` --uses--> `AbstractStrategy`  [INFERRED]
  api/main.py → strategies/base.py
- `RiskManager` --uses--> `Signal`  [INFERRED]
  risk/manager.py → strategies/base.py

## Import Cycles
- None detected.

## Communities (53 total, 19 thin omitted)

### Community 0 - "models.py"
Cohesion: 0.05
Nodes (18): Base, TimestampMixin, UUIDMixin, BacktestResult, BacktestRun, Candle, DailyPnL, Order (+10 more)

### Community 1 - "api"
Cohesion: 0.05
Nodes (46): build, command, container_name, depends_on, env_file, environment, ports, restart (+38 more)

### Community 2 - "main.py"
Cohesion: 0.07
Nodes (12): BacktestRequest, get_portfolio(), get_universe(), health_check(), HealthResponse, market_status(), run_backtest(), check_database_health() (+4 more)

### Community 3 - "BacktestReport"
Cohesion: 0.08
Nodes (3): BacktestReport, BacktestTrade, ReportGenerator

### Community 4 - "config/manager.py"
Cohesion: 0.06
Nodes (11): ApiSettings, BacktestSettings, BrokerSettings, DatabaseSettings, get_settings(), LoggingSettings, MarketSettings, RiskSettings (+3 more)

### Community 5 - "RiskManager"
Cohesion: 0.10
Nodes (12): RiskCheckResult, RiskManager, _buy_signal(), test_risk_blocks_duplicate_position(), test_risk_blocks_max_positions(), test_risk_blocks_when_daily_loss_hit(), test_risk_check_approved(), test_risk_is_trading_allowed() (+4 more)

### Community 6 - "fetch_candles_chunked"
Cohesion: 0.09
Nodes (11): CandleInterval, _date_chunks(), fetch_candles_chunked(), fetch_candles_single(), _fmt(), _response_to_dataframe(), _make_candle_response(), TestDateChunks (+3 more)

### Community 7 - "MockBroker"
Cohesion: 0.14
Nodes (15): OrderRequest, OrderType, TransactionType, MockBroker, test_broker_reset(), test_cancel_order(), test_cash_decrements_on_buy(), test_get_candles() (+7 more)

### Community 8 - "LiveDataFeed"
Cohesion: 0.10
Nodes (5): get_ltp_rest(), LiveDataFeed, _make_instrument(), TestGetLtpRest, TestLiveDataFeed

### Community 9 - "GrowwBroker"
Cohesion: 0.09
Nodes (5): BrokerAuthError, BrokerDataError, BrokerError, LiveTradingBlockedError, GrowwBroker

### Community 10 - "engine.py"
Cohesion: 0.09
Nodes (4): BacktestEngine, OpenPosition, AbstractStrategy, Signal

### Community 11 - "logging_config.py"
Cohesion: 0.10
Nodes (6): get_logger(), _intercept_stdlib_logging(), _InterceptHandler, _json_serializer(), _redact_sensitive(), setup_logging()

### Community 12 - "broker/base.py"
Cohesion: 0.13
Nodes (5): BrokerOrderError, OrderResponse, OrderStatus, ProductType, Quote

### Community 13 - "test_strategies.py"
Cohesion: 0.14
Nodes (3): SignalType, test_ema_strategy_requires_min_candles(), test_strategy_validate_dataframe_missing_col()

### Community 14 - "TokenCache"
Cohesion: 0.15
Nodes (4): get_api_token(), TokenCache, TestGetApiToken, TestTokenCache

### Community 16 - "test_groww_client.py"
Cohesion: 0.12
Nodes (6): get_ohlc_rest(), get_quote_rest(), groww_client(), mock_groww_api(), TestGetOhlcRest, TestGetQuoteRest

### Community 17 - "PortfolioManager"
Cohesion: 0.15
Nodes (3): PortfolioManager, PortfolioSnapshot, PositionRecord

### Community 18 - "EMACrossoverStrategy"
Cohesion: 0.15
Nodes (7): EMACrossoverStrategy, _make_crossover_df(), test_candles_to_dataframe(), test_ema_bearish_crossover_produces_sell(), test_ema_bullish_crossover_produces_buy(), test_ema_signal_has_valid_stop_loss_and_tp(), test_ema_strategy_returns_list()

### Community 21 - "RSIMeanReversionStrategy"
Cohesion: 0.16
Nodes (5): RSIMeanReversionStrategy, test_backtest_with_rsi_strategy(), test_ema_all_signals_are_buy_or_sell(), test_rsi_all_signals_valid(), test_rsi_strategy_returns_list()

### Community 24 - "connection.py"
Cohesion: 0.16
Nodes (4): _build_database_url(), create_engine(), get_db_session(), get_session()

### Community 26 - "test_backtest.py"
Cohesion: 0.23
Nodes (12): _build_engine(), test_backtest_commission_reduces_pnl(), test_backtest_initial_capital_preserved(), test_backtest_max_drawdown_non_negative(), test_backtest_pnl_sum_matches_capital_change(), test_backtest_report_has_correct_ticker(), test_backtest_runs_without_error(), test_backtest_summary_contains_header() (+4 more)

### Community 27 - "authentication.py"
Cohesion: 0.18
Nodes (3): capability_report(), obtain_access_token(), TestObtainAccessToken

### Community 29 - "settings.yaml"
Cohesion: 0.17
Nodes (11): dashboard, chart_theme, port, refresh_interval_sec, notifications, events, telegram, portfolio (+3 more)

### Community 30 - "params"
Cohesion: 0.17
Nodes (12): enabled, name, params, deviation_pct, fast_period, overbought, oversold, rsi_period (+4 more)

### Community 31 - "broker"
Cohesion: 0.17
Nodes (12): broker, api_base_url, exchange, live_trading_enabled, name, paper_trading_enabled, rate_limit_calls_per_minute, request_timeout_sec (+4 more)

### Community 32 - "conftest.py"
Cohesion: 0.25
Nodes (5): ema_strategy(), mock_broker(), risk_manager(), rsi_strategy(), sample_candles_df()

### Community 35 - "market"
Cohesion: 0.20
Nodes (10): market, avoid_first_minutes, avoid_last_minutes, candle_interval_minutes, exchange, market_close_time, market_open_time, nifty100_symbols (+2 more)

### Community 36 - "risk"
Cohesion: 0.22
Nodes (9): risk, max_daily_loss_pct, max_open_positions, max_position_size_pct, max_risk_per_trade_pct, stop_loss_pct, take_profit_pct, trailing_stop_enabled (+1 more)

### Community 40 - "application"
Cohesion: 0.29
Nodes (7): application, debug, env, log_level, name, timezone, version

### Community 41 - "api"
Cohesion: 0.33
Nodes (6): api, cors_origins, host, port, reload, workers

### Community 42 - "backtest"
Cohesion: 0.33
Nodes (6): backtest, commission_pct, data_source, end_date, slippage_pct, start_date

### Community 43 - "database"
Cohesion: 0.33
Nodes (6): database, echo_sql, max_overflow, pool_recycle, pool_size, pool_timeout

### Community 44 - "logging"
Cohesion: 0.33
Nodes (6): logging, format, level, log_file, retention, rotation

### Community 46 - "trading"
Cohesion: 0.50
Nodes (4): trading, currency, initial_capital, mode

## Knowledge Gaps
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GrowwClient` connect `GrowwClient` to `.get_ltp`, `.get_positions`, `.get_instrument`, `test_groww_client.py`, `_with_retry`, `TestGrowwClientOrders`, `LiveTradingBlockedError`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `MockBroker` (e.g. with `run_backtest()` and `AccountInfo`) actually correct?**
  _`MockBroker` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Should `models.py` be split into smaller, more focused modules?**
  _Cohesion score 0.053939714436805924 - nodes in this community are weakly interconnected._
- **Why does `MockBroker` connect `MockBroker` to `conftest.py`, `main.py`, `Position`, `AccountInfo`, `GrowwBroker`, `broker/base.py`, `test_strategies.py`, `AbstractBroker`, `Candle`, `test_backtest.py`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `GrowwClient` (e.g. with `groww_client()` and `TestGrowwClientInit`) actually correct?**
  _`GrowwClient` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `api` be split into smaller, more focused modules?**
  _Cohesion score 0.04625346901017576 - nodes in this community are weakly interconnected._
- **Why does `BacktestReport` connect `BacktestReport` to `test_backtest.py`, `engine.py`, `logging_config.py`, `RSIMeanReversionStrategy`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._