import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from app.core.actors import Actor
from app.core.exceptions import ConflictError, UnauthorizedError
from app.modules.auth.models import AuthSession
from app.modules.auth.repository import SessionRepository
from app.modules.auth.service import AuthService
from app.modules.auth.tokens import hash_token
from app.modules.users.repository import UserRepository
from tests.unit.test_user_service import InMemoryUserRepository, RecordingAudit, service_for


class InMemorySessions:
    def __init__(self) -> None:
        self.rows: list[AuthSession] = []

    async def add(self, row: AuthSession) -> AuthSession:
        self.rows.append(row)
        return row

    async def get_by_id(self, session_id: uuid.UUID) -> AuthSession | None:
        return next((row for row in self.rows if row.id == session_id), None)

    async def get_active(self, token_hash: str, now: datetime) -> AuthSession | None:
        return next(
            (
                row
                for row in self.rows
                if row.token_hash == token_hash and row.revoked_at is None and row.expires_at > now
            ),
            None,
        )

    async def flush(self) -> None:
        return None


def build_auth(
    repository: InMemoryUserRepository | None = None,
) -> tuple[AuthService, InMemoryUserRepository, InMemorySessions, RecordingAudit]:
    users = repository or InMemoryUserRepository()
    sessions = InMemorySessions()
    audit = RecordingAudit()
    service = AuthService(
        users=cast(UserRepository, users),
        user_service=service_for(users, audit),
        sessions=cast(SessionRepository, sessions),
        audit=audit,
        session_ttl=timedelta(minutes=30),
    )
    return service, users, sessions, audit


async def test_bootstrap_stores_a_hash_of_the_token_and_audits_identifiers() -> None:
    service, _users, sessions, audit = build_auth()
    result = await service.bootstrap_admin(
        display_name="Ada",
        email="Ada@Example.com",
        password="password123",
    )

    assert result.user.email == "ada@example.com"
    assert result.user.role == "admin"
    assert result.user.password_hash is not None
    assert result.user.password_hash != "password123"
    assert sessions.rows[0].token_hash == hash_token(result.access_token)
    assert result.access_token not in sessions.rows[0].token_hash
    rendered = str(audit.events)
    assert "password123" not in rendered
    assert result.access_token not in rendered
    assert [event["action"] for event in audit.events] == ["user.created", "session.created"]


async def test_second_bootstrap_is_rejected() -> None:
    service, _users, _sessions, _audit = build_auth()
    await service.bootstrap_admin(
        display_name="Ada",
        email="ada@example.com",
        password="password123",
    )
    with pytest.raises(ConflictError) as caught:
        await service.bootstrap_admin(
            display_name="Grace",
            email="grace@example.com",
            password="password123",
        )
    assert caught.value.code == "bootstrap_closed"


async def test_login_failures_share_one_message() -> None:
    service, users, _sessions, _audit = build_auth()
    await service.bootstrap_admin(
        display_name="Ada",
        email="ada@example.com",
        password="password123",
    )
    await service_for(users).create_user(
        Actor(user_id=uuid.uuid4(), role="admin", session_id=uuid.uuid4()),
        display_name="Pat",
        email="pat@example.com",
        is_active=True,
    )

    wrong = await _login_error(service, "ada@example.com", "wrong-password")
    missing = await _login_error(service, "missing@example.com", "password123")
    patient = await _login_error(service, "pat@example.com", "password123")
    assert wrong == missing == patient == "Invalid email or password."


async def test_logout_revokes_the_session() -> None:
    service, _users, sessions, _audit = build_auth()
    result = await service.bootstrap_admin(
        display_name="Ada",
        email="ada@example.com",
        password="password123",
    )
    actor = await service.authenticate(result.access_token)
    await service.logout(actor)
    assert sessions.rows[0].revoked_at is not None
    with pytest.raises(UnauthorizedError) as caught:
        await service.authenticate(result.access_token)
    assert caught.value.code == "authentication_required"


async def test_expired_session_is_rejected() -> None:
    service, _users, sessions, _audit = build_auth()
    result = await service.bootstrap_admin(
        display_name="Ada",
        email="ada@example.com",
        password="password123",
    )
    sessions.rows[0].expires_at = datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(UnauthorizedError):
        await service.authenticate(result.access_token)


async def _login_error(service: AuthService, email: str, password: str) -> str:
    with pytest.raises(UnauthorizedError) as caught:
        await service.login(email=email, password=password)
    assert caught.value.code == "invalid_credentials"
    return caught.value.message
