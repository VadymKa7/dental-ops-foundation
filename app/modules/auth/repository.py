"""SQLAlchemy persistence for sessions. No business rules live here."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import AuthSession


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, row: AuthSession) -> AuthSession:
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_id(self, session_id: uuid.UUID) -> AuthSession | None:
        return await self._session.get(AuthSession, session_id)

    async def flush(self) -> None:
        await self._session.flush()

    async def get_active(self, token_hash: str, now: datetime) -> AuthSession | None:
        statement = select(AuthSession).where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
