"""PostgreSQL fixtures for API tests.

SQLite is intentionally unsupported. Set TEST_DATABASE_URL to an empty
asyncpg database before running this package. The fixture applies Alembic
migrations in a subprocess so its event loop stays off the pytest loop.
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import Environment, Settings, get_settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if os.environ.get("REQUIRE_INTEGRATION") == "1":
            pytest.fail("TEST_DATABASE_URL must be set when REQUIRE_INTEGRATION=1.")
        pytest.skip(
            "TEST_DATABASE_URL is not set. Integration tests need an empty PostgreSQL "
            "database and the postgresql+asyncpg driver. See README.md."
        )
    if not url.startswith("postgresql+asyncpg://"):
        pytest.fail(
            "TEST_DATABASE_URL must start with postgresql+asyncpg://. "
            "SQLite is not a substitute for this application's driver."
        )
    return url


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> Iterator[str]:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    get_settings.cache_clear()
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        pytest.fail(f"Alembic upgrade failed for TEST_DATABASE_URL.\n{detail}")
    try:
        yield test_database_url
    finally:
        get_settings.cache_clear()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture
async def client(migrated_database: str) -> AsyncIterator[AsyncClient]:
    application = create_app(
        Settings(
            database_url=migrated_database,
            environment=Environment.TEST,
            log_level="WARNING",
            debug=False,
            database_connect_timeout_seconds=5,
        )
    )
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
        async with application.state.engine.begin() as connection:
            await connection.execute(text("TRUNCATE TABLE users"))
