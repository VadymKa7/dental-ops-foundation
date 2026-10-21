"""FastAPI dependencies for the request-scoped database session."""

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield one transaction for the current request.

    The route runs inside that transaction. Cleanup commits when the route
    returns normally and rolls back when the route raises. The repository
    flushes writes, so unique-constraint failures surface before commit.
    """
    session_factory = cast(
        async_sessionmaker[AsyncSession],
        request.app.state.session_factory,
    )
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
