"""Shared constructors for API tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Environment, Settings
from app.main import create_app

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://dental:dental@127.0.0.1:1/dental"


def build_app(
    *,
    database_url: str = "postgresql+asyncpg://dental:dental@127.0.0.1:5432/dental",
    database_connect_timeout_seconds: float = 1.0,
) -> FastAPI:
    settings = Settings(
        database_url=database_url,
        environment=Environment.TEST,
        log_level="WARNING",
        debug=False,
        database_connect_timeout_seconds=database_connect_timeout_seconds,
    )
    return create_app(settings)


@asynccontextmanager
async def open_client(application: FastAPI) -> AsyncIterator[AsyncClient]:
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
