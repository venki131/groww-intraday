"""Initial schema - all tables.

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables."""

    # --- symbols ---
    op.create_table(
        "symbols",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("exchange", sa.String(10), nullable=False, server_default="NSE"),
        sa.Column("segment", sa.String(10), nullable=False, server_default="EQ"),
        sa.Column("isin", sa.String(20), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tick_size", sa.Numeric(10, 4), nullable=False, server_default="0.05"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("in_nifty100", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", name="uq_symbol_ticker"),
    )
    op.create_index("ix_symbols_ticker", "symbols", ["ticker"])

    # --- candles ---
    op.create_table(
        "candles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("open", sa.Numeric(12, 4), nullable=False),
        sa.Column("high", sa.Numeric(12, 4), nullable=False),
        sa.Column("low", sa.Numeric(12, 4), nullable=False),
        sa.Column("close", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("vwap", sa.Numeric(12, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "timestamp", "interval_minutes", name="uq_candle"),
    )
    op.create_index("ix_candles_ticker", "candles", ["ticker"])
    op.create_index("ix_candles_timestamp", "candles", ["timestamp"])
    op.create_index("ix_candle_ticker_ts", "candles", ["ticker", "timestamp"])

    # --- orders ---
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broker_order_id", sa.String(100), nullable=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("exchange", sa.String(10), nullable=False, server_default="NSE"),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("transaction_type", sa.String(10), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(12, 4), nullable=True),
        sa.Column("trigger_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("filled_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("average_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("mode", sa.String(20), nullable=False, server_default="backtest"),
        sa.Column("strategy_name", sa.String(100), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_ticker", "orders", ["ticker"])

    # --- trades ---
    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("transaction_type", sa.String(10), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(12, 4), nullable=False),
        sa.Column("brokerage", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("taxes", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("strategy_name", sa.String(100), nullable=True),
        sa.Column("mode", sa.String(20), nullable=False, server_default="backtest"),
        sa.Column("traded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trades_ticker", "trades", ["ticker"])
    op.create_index("ix_trade_ticker_date", "trades", ["ticker", "traded_at"])

    # --- positions ---
    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("average_buy_price", sa.Numeric(12, 4), nullable=False),
        sa.Column("current_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("unrealised_pnl", sa.Numeric(14, 4), nullable=True),
        sa.Column("realised_pnl", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("stop_loss", sa.Numeric(12, 4), nullable=True),
        sa.Column("take_profit", sa.Numeric(12, 4), nullable=True),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("strategy_name", sa.String(100), nullable=True),
        sa.Column("mode", sa.String(20), nullable=False, server_default="backtest"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_positions_ticker", "positions", ["ticker"])
    op.create_index("ix_positions_is_open", "positions", ["is_open"])

    # --- daily_pnl ---
    op.create_table(
        "daily_pnl",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("winning_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("losing_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gross_pnl", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("brokerage", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("net_pnl", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("strategy_name", sa.String(100), nullable=True),
        sa.Column("mode", sa.String(20), nullable=False, server_default="backtest"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_date", "ticker", "strategy_name", "mode", name="uq_daily_pnl"),
    )
    op.create_index("ix_daily_pnl_trade_date", "daily_pnl", ["trade_date"])
    op.create_index("ix_daily_pnl_ticker", "daily_pnl", ["ticker"])

    # --- backtest_runs ---
    op.create_table(
        "backtest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("strategy_name", sa.String(100), nullable=False),
        sa.Column("universe", sa.String(50), nullable=False, server_default="NIFTY100"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("initial_capital", sa.Numeric(14, 4), nullable=False),
        sa.Column("final_capital", sa.Numeric(14, 4), nullable=True),
        sa.Column("total_return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("cagr_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_drawdown_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("win_rate_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("total_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parameters", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- backtest_results ---
    op.create_table(
        "backtest_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_price", sa.Numeric(12, 4), nullable=False),
        sa.Column("exit_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("gross_pnl", sa.Numeric(14, 4), nullable=True),
        sa.Column("net_pnl", sa.Numeric(14, 4), nullable=True),
        sa.Column("exit_reason", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["backtest_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("backtest_results")
    op.drop_table("backtest_runs")
    op.drop_table("daily_pnl")
    op.drop_table("positions")
    op.drop_table("trades")
    op.drop_table("orders")
    op.drop_table("candles")
    op.drop_table("symbols")