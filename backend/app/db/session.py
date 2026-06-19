"""
db/session.py
─────────────
Async SQLAlchemy engine + session factory.
RDS PostgreSQL via asyncpg.
Connection pool tuned for ECS Fargate container sizing.
"""

from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────

def _make_engine() -> AsyncEngine:
    kwargs: dict = dict(
        echo=settings.DATABASE_ECHO,
        pool_pre_ping=True,          # detect stale connections
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
        pool_recycle=1800,           # recycle connections every 30 min
        connect_args={
            "server_settings": {
                "application_name": "noteflow-api",
                "jit": "off",        # PostgreSQL JIT off for short queries
            },
            "command_timeout": 30,
        },
    )
    # Use NullPool for test / migration contexts
    if settings.ENVIRONMENT == "test":
        kwargs = {"echo": True, "poolclass": NullPool}

    return create_async_engine(settings.database_url, **kwargs)


engine: AsyncEngine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── Dependency ────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields a database session per request.
    Rolls back on exception; always closes at end of request.
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


# ── Health check helper ──────────────────────────────────────────

async def check_db_connection() -> bool:
    """Used by /health endpoint."""
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        return False
