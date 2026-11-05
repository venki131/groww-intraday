"""Market data schema: instruments, index_membership, candles_5m, data_download_jobs.

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # instruments                                                           #
    # ------------------------------------------------------------------ #
    op.create_table(
        "instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticker",       sa.String(20),  nullable=False),
        sa.Column("name",         sa.String(255), nullable=False),
        sa.Column("isin",         sa.String(12),  nullable=True),
        sa.Column("groww_symbol", sa.String(50),  nullable=True),
        sa.Column("exchange",     sa.String(10),  nullable=False, server_default="NSE"),
        sa.Column("segment",      sa.String(10),  nullable=False, server_default="EQ"),
        sa.Column("sector",       sa.String(100), nullable=True),
        sa.Column("industry",     sa.String(100), nullable=True),
        sa.Column("is_active",    sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("created_at",   sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",   sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_instruments_ticker",  "instruments", ["ticker"],  unique=True)
    op.create_index("ix_instruments_isin",    "instruments", ["isin"],    unique=False)
    op.create_index("ix_instruments_sector",  "instruments", ["sector"],  unique=False)
    op.create_index("ix_instruments_active",  "instruments", ["is_active"], unique=False)

    # ------------------------------------------------------------------ #
    # index_membership                                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "index_membership",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("index_name",      sa.String(50),  nullable=False),
        sa.Column("instrument_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ticker",          sa.String(20),  nullable=False),
        sa.Column("effective_from",  sa.Date(),       nullable=False),
        sa.Column("effective_to",    sa.Date(),       nullable=True),   # NULL = current member
        sa.Column("source",          sa.String(100),  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"],
            name="fk_index_membership_instrument",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_index_membership_index_ticker",
        "index_membership",
        ["index_name", "ticker"],
        unique=False,
    )
    op.create_index(
        "ix_index_membership_effective",
        "index_membership",
        ["index_name", "effective_from", "effective_to"],
        unique=False,
    )
    # Unique constraint used by ON CONFLICT DO UPDATE in db_seed
    op.create_unique_constraint(
        "uq_index_membership",
        "index_membership",
        ["index_name", "ticker", "effective_from"],
    )

    # ------------------------------------------------------------------ #
    # candles_5m                                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "candles_5m",
        sa.Column("ticker",        sa.String(20),         nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open",          sa.Numeric(12, 4),     nullable=False),
        sa.Column("high",          sa.Numeric(12, 4),     nullable=False),
        sa.Column("low",           sa.Numeric(12, 4),     nullable=False),
        sa.Column("close",         sa.Numeric(12, 4),     nullable=False),
        sa.Column("volume",        sa.BigInteger(),        nullable=False),
        sa.Column("vwap",          sa.Numeric(12, 4),     nullable=True),
        # quality flags
        sa.Column("is_zero_volume",  sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_interpolated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_ohlc_error",  sa.Boolean(), nullable=False, server_default="false"),
        # provenance
        sa.Column("source",       sa.String(50),          nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        # audit
        sa.Column("created_at",   sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",   sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("ticker", "timestamp_utc", name="pk_candles_5m"),
    )
    # Covering index: typical query pattern is (ticker, timestamp range)
    op.create_index(
        "ix_candles_5m_ticker_ts",
        "candles_5m",
        ["ticker", "timestamp_utc"],
        unique=True,
    )
    # Index for quality-flag queries (find all zero-volume candles etc.)
    op.create_index(
        "ix_candles_5m_zero_volume",
        "candles_5m",
        ["ticker", "is_zero_volume"],
        unique=False,
        postgresql_where=sa.text("is_zero_volume = true"),
    )

    # ------------------------------------------------------------------ #
    # data_download_jobs                                                    #
    # ------------------------------------------------------------------ #
    op.create_table(
        "data_download_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticker",           sa.String(20),   nullable=True),
        sa.Column("index_name",       sa.String(50),   nullable=True),
        sa.Column("start_date",       sa.Date(),        nullable=False),
        sa.Column("end_date",         sa.Date(),        nullable=False),
        sa.Column("interval_minutes", sa.Integer(),     nullable=False, server_default="5"),
        sa.Column("status",           sa.String(20),   nullable=False, server_default="pending"),
        # progress counters
        sa.Column("candles_downloaded",          sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candles_expected",            sa.Integer(), nullable=True),
        sa.Column("candles_skipped_duplicates",  sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candles_rejected_quality",    sa.Integer(), nullable=False, server_default="0"),
        # error capture
        sa.Column("error_message", sa.Text(), nullable=True),
        # audit
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ddj_status",  "data_download_jobs", ["status"],  unique=False)
    op.create_index("ix_ddj_ticker",  "data_download_jobs", ["ticker"],  unique=False)


def downgrade() -> None:
    op.drop_table("data_download_jobs")

    op.drop_index("ix_candles_5m_zero_volume", table_name="candles_5m")
    op.drop_index("ix_candles_5m_ticker_ts",   table_name="candles_5m")
    op.drop_table("candles_5m")

    op.drop_constraint("uq_index_membership",          "index_membership", type_="unique")
    op.drop_index("ix_index_membership_effective",     table_name="index_membership")
    op.drop_index("ix_index_membership_index_ticker",  table_name="index_membership")
    op.drop_table("index_membership")

    op.drop_index("ix_instruments_active",  table_name="instruments")
    op.drop_index("ix_instruments_sector",  table_name="instruments")
    op.drop_index("ix_instruments_isin",    table_name="instruments")
    op.drop_index("ix_instruments_ticker",  table_name="instruments")
    op.drop_table("instruments")