"""Make application import safe for unit tests.

The ASGI module builds Settings on import. Unit tests do not need a running
database, but they do need a syntactically valid asyncpg URL in the environment
when `app.main` is imported. Integration tests use TEST_DATABASE_URL instead.
"""

import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://dental:dental@127.0.0.1:5432/dental",
)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
