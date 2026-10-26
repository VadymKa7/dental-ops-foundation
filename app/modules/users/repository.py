"""SQLAlchemy persistence for users. No business rules live here."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from app.modules.users.roles import STAFF_ROLES


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_users(self, *, limit: int, offset: int) -> list[User]:
        statement = (
            select(User)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.scalar(select(func.count()).select_from(User))
        return int(result or 0)

    async def count_staff(self) -> int:
        statement = select(func.count()).select_from(User).where(User.role.in_(STAFF_ROLES))
        result = await self._session.scalar(statement)
        return int(result or 0)
