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
from src.backend.core.logging import get_logger

logger = get_logger(__name__)


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
            max_size=10,
            kwargs={"autocommit": True},
            open=False,
        )
        await pool.open()
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
            pool_pre_ping=True,
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
            error_detail=str(error),
        )


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
