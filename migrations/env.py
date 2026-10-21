"""Alembic environment.

The database URL comes from Settings, not from alembic.ini, so the password
is not copied into a second config file. Models are imported here because
this is the migration composition root. `app.db` does not import feature modules.
Run Alembic from the repository root. The application does not call it on startup.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.modules.users.models import User

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

target_metadata = Base.metadata

if User.__tablename__ not in target_metadata.tables:
    raise RuntimeError("User model was not registered on SQLAlchemy metadata.")


def _database_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    connectable = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_online())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
