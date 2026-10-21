import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings, get_settings


def test_database_url_must_use_asyncpg() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        Settings(database_url="postgresql://dental:dental@localhost:5432/dental")


def test_sqlite_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        Settings(database_url="sqlite+aiosqlite:///tmp/dental.db")


def test_production_cannot_enable_debug() -> None:
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        Settings(
            database_url="postgresql+asyncpg://dental:dental@localhost:5432/dental",
            environment=Environment.PRODUCTION,
            debug=True,
        )


def test_api_prefix_strips_a_trailing_slash() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://dental:dental@localhost:5432/dental",
        api_prefix="/api/v1/",
    )
    assert settings.api_prefix == "/api/v1"


def test_redis_url_defaults_without_being_required() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://dental:dental@localhost:5432/dental",
    )
    assert settings.redis_url == "redis://localhost:6379/0"


def test_get_settings_reads_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql+asyncpg://dental:dental@db.internal:5432/dental"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        assert get_settings().database_url == url
    finally:
        get_settings.cache_clear()
