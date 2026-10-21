"""Async engine and session factory.

This module does not import FastAPI. A future worker can call the same
functions, open a session, and invoke a service without an HTTP request.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_db_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=settings.database_connect_timeout_seconds,
        connect_args={"timeout": settings.database_connect_timeout_seconds},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit stays off so response mapping does not lazy-load after commit.
    # Async lazy loads are not supported and would raise if a handler touched an expired field.
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
