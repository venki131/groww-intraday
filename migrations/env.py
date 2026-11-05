"""
Alembic migration environment.

Configured for async PostgreSQL with SQLAlchemy 2.x.
Run migrations with:
    alembic upgrade head
    alembic revision --autogenerate -m "description"
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import Optional

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so Alembic can detect them for autogenerate
from database.base import Base
import database.models  # noqa: F401 - registers all models on Base.metadata

# ---------------------------------------------------------------------------
# Alembic Config
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLAlchemy metadata for autogenerate
target_metadata = Base.metadata


def _get_database_url() -> str:
    """
    Build sync database URL for Alembic (uses psycopg2).

    Returns:
        Sync connection string.
    """
    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL", "")
    # Ensure sync driver
    if "asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode (generates SQL script).

    Useful for reviewing changes before applying them.
    """
    url = _get_database_url() or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Execute pending migrations against an open connection.

    Args:
        connection: Active SQLAlchemy connection.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine."""
    url = _get_database_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (applies directly to the database)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()