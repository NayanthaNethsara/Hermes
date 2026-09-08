from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from psycopg_pool import AsyncConnectionPool
from sqlalchemy import JSON, DateTime, String, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.backend.core.config import get_settings
from src.backend.core.exceptions import (
    DatabaseUnavailableError,
    is_connectivity_error,
    summarize_error,
)
from src.backend.core.logging import get_logger

logger = get_logger(__name__)

CONNECT_TIMEOUT_SECONDS = 5.0
COMMAND_TIMEOUT_SECONDS = 60.0
POOL_RECYCLE_SECONDS = 1800


class Base(DeclarativeBase):
    pass


class ChatSessionModel(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    turns_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(String, nullable=True, default=None)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_connection_pool: AsyncConnectionPool | None = None


async def get_connection_pool() -> AsyncConnectionPool:
    global _connection_pool
    if _connection_pool is None:
        settings = get_settings()
        pool = AsyncConnectionPool(
            conninfo=settings.psycopg_dsn,
            min_size=1,
            max_size=10,
            # Without an explicit timeout, checking out a connection while
            # Postgres is down blocks for 30s before failing.
            timeout=CONNECT_TIMEOUT_SECONDS,
            kwargs={"autocommit": True, "connect_timeout": int(CONNECT_TIMEOUT_SECONDS)},
            open=False,
        )
        try:
            await pool.open()
        except Exception as error:
            # Do not cache a pool that never opened, so the next call can retry
            # once Postgres is reachable again.
            await pool.close()
            logger.warning("connection_pool_open_failed", error=summarize_error(error))
            raise DatabaseUnavailableError() from error
        _connection_pool = pool
    return _connection_pool


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            # pool_pre_ping discards connections that died while Postgres was
            # down; recycle keeps the pool from holding them indefinitely.
            pool_pre_ping=True,
            pool_recycle=POOL_RECYCLE_SECONDS,
            connect_args={
                "timeout": CONNECT_TIMEOUT_SECONDS,
                "command_timeout": COMMAND_TIMEOUT_SECONDS,
            },
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def init_database() -> None:
    engine = get_engine()
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS summary TEXT;"))
        logger.info("database_initialized_successfully")
    except Exception as error:
        logger.warning(
            "database_initialization_deferred",
            error_detail=summarize_error(error),
        )


async def check_database_health() -> bool:
    try:
        engine = get_engine()
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1;"))
        return True
    except Exception as error:
        logger.warning("database_healthcheck_failed", error=summarize_error(error))
        return False


async def close_database() -> None:
    global _engine, _session_factory, _connection_pool
    if _connection_pool is not None:
        try:
            await _connection_pool.close()
        except Exception as error:
            logger.warning("connection_pool_close_failed", error=summarize_error(error))
        _connection_pool = None
    if _engine is not None:
        try:
            await _engine.dispose()
        except Exception as error:
            logger.warning("engine_dispose_failed", error=summarize_error(error))
        _engine = None
        _session_factory = None
    logger.info("database_connections_closed")


def as_database_error(error: BaseException) -> BaseException:
    """Relabel an unreachable Postgres as DatabaseUnavailableError.

    asyncpg raises a bare OSError for a refused connection, which says nothing
    about which service is down; anything that is not a connectivity failure is
    returned untouched so real bugs keep their own type.
    """
    if isinstance(error, DatabaseUnavailableError):
        return error
    if is_connectivity_error(error):
        return DatabaseUnavailableError()
    return error


async def safe_rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception as error:
        logger.warning("session_rollback_failed", error=summarize_error(error))


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as error:
            await safe_rollback(session)
            translated = as_database_error(error)
            if translated is error:
                raise
            raise translated from error


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as error:
            await safe_rollback(session)
            translated = as_database_error(error)
            if translated is error:
                raise
            raise translated from error
