"""
PostgreSQL async database connection using SQLAlchemy 2.x.

Provides:
- Async engine with connection pooling
- AsyncSession factory
- FastAPI dependency injection helper ``get_db_session``
- Health check utility
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

from config.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Engine construction
# ---------------------------------------------------------------------------

def _build_database_url() -> str:
    """
    Build the async database URL from environment variables.

    Returns:
        Async SQLAlchemy connection string.

    Raises:
        ValueError: If required environment variables are missing.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        # Ensure async driver prefix
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "groww_intraday")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


def create_engine(
    database_url: str | None = None,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_timeout: int = 30,
    pool_recycle: int = 1800,
    echo: bool = False,
) -> AsyncEngine:
    """
    Create and return a configured async SQLAlchemy engine.

    Args:
        database_url: Override database URL (uses env vars if None).
        pool_size: Number of connections to keep open in the pool.
        max_overflow: Extra connections allowed beyond pool_size.
        pool_timeout: Seconds to wait for a connection before raising.
        pool_recycle: Recycle connections older than this many seconds.
        echo: If True, log all SQL statements (dev only).

    Returns:
        Configured AsyncEngine instance.
    """
    url = database_url or _build_database_url()
    logger.info("Creating database engine", host=url.split("@")[-1] if "@" in url else "?")

    return create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        echo=echo,
        future=True,
    )


# Module-level singletons
engine: AsyncEngine = create_engine(
    echo=os.getenv("DB_ECHO_SQL", "false").lower() == "true"
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session per request.

    Automatically commits on success and rolls back on exception.

    Yields:
        An active AsyncSession.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Context manager for scripts / background tasks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for getting a DB session outside FastAPI.

    Usage:
        async with get_session() as db:
            result = await db.execute(select(Trade))

    Yields:
        An active AsyncSession.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def check_database_health() -> dict[str, str]:
    """
    Ping the database and return a health status dict.

    Returns:
        Dict with 'status' ('ok' or 'error') and 'detail'.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "detail": "Database connection healthy"}
    except Exception as exc:
        logger.error("Database health check failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}