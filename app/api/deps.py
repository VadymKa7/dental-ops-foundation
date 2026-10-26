"""FastAPI dependencies for the request-scoped database session and services."""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.actors import Actor
from app.core.config import Settings
from app.modules.audit.repository import AuditRepository
from app.modules.audit.service import AuditService
from app.modules.auth.repository import SessionRepository
from app.modules.auth.service import AuthService
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService

_bearer_scheme = HTTPBearer(auto_error=False)


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


def get_audit_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuditService:
    return AuditService(AuditRepository(session))


def get_user_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> UserService:
    return UserService(UserRepository(session), audit)


def get_auth_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> AuthService:
    settings = cast(Settings, request.app.state.settings)
    return AuthService(
        users=UserRepository(session),
        user_service=user_service,
        sessions=SessionRepository(session),
        audit=audit,
        session_ttl=timedelta(minutes=settings.session_ttl_minutes),
    )


async def get_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> Actor:
    token = credentials.credentials if credentials is not None else None
    if token is not None and not token.strip():
        token = None
    return await auth_service.authenticate(token)
