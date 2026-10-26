"""Sign-in rules.

Login failures share one message. A missing account, a patient, an inactive
staff member, and a wrong password are not distinguished.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.actors import Actor
from app.core.exceptions import UnauthorizedError
from app.core.passwords import dummy_password_hash, verify_password
from app.modules.audit.recorder import AuditRecorder
from app.modules.auth.models import AuthSession
from app.modules.auth.repository import SessionRepository
from app.modules.auth.tokens import hash_token, new_token
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.roles import STAFF_ROLES
from app.modules.users.service import UserService, normalize_email

_INVALID_LOGIN = "Invalid email or password."
_AUTH_REQUIRED = "Authentication required."


@dataclass(frozen=True, slots=True)
class LoginResult:
    access_token: str
    expires_at: datetime
    user: User


class AuthService:
    def __init__(
        self,
        *,
        users: UserRepository,
        user_service: UserService,
        sessions: SessionRepository,
        audit: AuditRecorder,
        session_ttl: timedelta,
    ) -> None:
        self._users = users
        self._user_service = user_service
        self._sessions = sessions
        self._audit = audit
        self._session_ttl = session_ttl

    async def bootstrap_admin(
        self,
        *,
        display_name: str,
        email: str,
        password: str,
    ) -> LoginResult:
        user = await self._user_service.create_first_admin(
            display_name=display_name,
            email=email,
            password=password,
        )
        return await self._open_session(user)

    async def login(self, *, email: str, password: str) -> LoginResult:
        normalized_email = normalize_email(email)
        user = await self._users.get_by_email(normalized_email)
        stored_hash = user.password_hash if user is not None else None
        password_matches = await self._password_matches(password, stored_hash)
        if (
            user is None
            or not user.is_active
            or user.role not in STAFF_ROLES
            or stored_hash is None
            or not password_matches
        ):
            raise UnauthorizedError(_INVALID_LOGIN, code="invalid_credentials")
        return await self._open_session(user)

    async def authenticate(self, token: str | None) -> Actor:
        if token is None:
            raise UnauthorizedError(_AUTH_REQUIRED, code="authentication_required")
        row = await self._sessions.get_active(hash_token(token), datetime.now(UTC))
        if row is None:
            raise UnauthorizedError(_AUTH_REQUIRED, code="authentication_required")
        user = await self._users.get_by_id(row.user_id)
        if user is None or not user.is_active or user.role not in STAFF_ROLES:
            raise UnauthorizedError(_AUTH_REQUIRED, code="authentication_required")
        return Actor(user_id=user.id, role=user.role, session_id=row.id)

    async def logout(self, actor: Actor) -> None:
        row = await self._sessions.get_by_id(actor.session_id)
        if row is None or row.revoked_at is not None:
            raise UnauthorizedError(_AUTH_REQUIRED, code="authentication_required")
        row.revoked_at = datetime.now(UTC)
        await self._sessions.flush()
        await self._audit.record(
            actor_user_id=actor.user_id,
            action="session.revoked",
            resource_type="session",
            resource_id=row.id,
        )

    async def _open_session(self, user: User) -> LoginResult:
        now = datetime.now(UTC)
        raw_token = new_token()
        row = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=now + self._session_ttl,
            revoked_at=None,
            created_at=now,
        )
        await self._sessions.add(row)
        await self._audit.record(
            actor_user_id=user.id,
            action="session.created",
            resource_type="session",
            resource_id=row.id,
        )
        return LoginResult(access_token=raw_token, expires_at=row.expires_at, user=user)

    async def _password_matches(self, password: str, password_hash: str | None) -> bool:
        candidate = (
            password_hash
            if password_hash is not None
            else await asyncio.to_thread(dummy_password_hash)
        )
        return await asyncio.to_thread(verify_password, password, candidate)
