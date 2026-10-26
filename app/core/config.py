"""Environment-backed settings.

The cached Settings object is immutable after it is built. Engine and session
objects are not stored here; the application lifespan owns those.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Runtime configuration loaded from the process environment and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Dental Operations Intelligence"
    environment: Environment = Environment.LOCAL
    debug: bool = False
    log_level: LogLevel = "INFO"
    api_prefix: str = "/api/v1"
    database_url: str
    database_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    # Present so a future worker can share this configuration. The API does not open Redis.
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_minutes: int = Field(default=480, gt=0, le=60 * 24 * 14)

    @field_validator("database_url")
    @classmethod
    def database_url_must_use_asyncpg(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver.")
        return value

    @field_validator("api_prefix")
    @classmethod
    def api_prefix_must_be_absolute(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API prefix must start with '/'.")
        trimmed = value.rstrip("/")
        return trimmed or "/"

    @model_validator(mode="after")
    def production_disables_debug(self) -> Self:
        if self.environment is Environment.PRODUCTION and self.debug:
            raise ValueError("DEBUG must be false when ENVIRONMENT is production.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process settings.

    Tests that change environment variables call `get_settings.cache_clear()` first.
    The ignore is required because mypy cannot see values loaded from the environment.
    """
    return Settings()  # type: ignore[call-arg]
