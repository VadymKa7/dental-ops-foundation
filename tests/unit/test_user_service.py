import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.actors import Actor
from app.core.exceptions import ConflictError, DomainValidationError, ForbiddenError, NotFoundError
from app.modules.audit.recorder import AuditRecorder
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.roles import PATIENT, STAFF_ROLES
from app.modules.users.service import UserService


class InMemoryUserRepository:
    """Stand-in used by service tests. It does not open a database session."""

    def __init__(self) -> None:
        self.users: list[User] = []
        self.raise_integrity_error = False

    async def add(self, user: User) -> User:
        if self.raise_integrity_error:
            raise IntegrityError("INSERT INTO users", {}, Exception("unique violation"))
        self.users.append(user)
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return next((user for user in self.users if user.id == user_id), None)

    async def get_by_email(self, email: str) -> User | None:
        if self.raise_integrity_error:
            return None
        return next((user for user in self.users if user.email == email), None)

    async def list_users(self, *, limit: int, offset: int) -> list[User]:
        ordered = sorted(self.users, key=lambda user: (user.created_at, user.id), reverse=True)
        return ordered[offset : offset + limit]

    async def count(self) -> int:
        return len(self.users)

    async def count_staff(self) -> int:
        return sum(1 for user in self.users if user.role in STAFF_ROLES)


class NullAudit:
    async def record(
        self,
        *,
        actor_user_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> None:
        return None


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def record(
        self,
        *,
        actor_user_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> None:
        self.events.append(
            {
                "actor_user_id": actor_user_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
            }
        )


def service_for(
    repository: InMemoryUserRepository,
    audit: AuditRecorder | None = None,
) -> UserService:
    return UserService(cast(UserRepository, repository), audit or NullAudit())


def admin_actor() -> Actor:
    return Actor(user_id=uuid.uuid4(), role="admin", session_id=uuid.uuid4())


def make_user(email: str, *, created_at: datetime | None = None) -> User:
    timestamp = created_at or datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        display_name="Ada",
        email=email,
        role=PATIENT,
        password_hash=None,
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


async def test_create_user_normalizes_name_and_email() -> None:
    repository = InMemoryUserRepository()
    user = await service_for(repository).create_user(
        admin_actor(),
        display_name="  Ada Lovelace  ",
        email="  Ada@Example.com ",
        is_active=True,
    )

    assert user.display_name == "Ada Lovelace"
    assert user.email == "ada@example.com"
    assert user.phone is None
    assert user.role == PATIENT
    assert user.password_hash is None
    assert user.is_active is True
    assert user.created_at == user.updated_at
    assert repository.users == [user]


async def test_create_user_stores_a_compact_phone() -> None:
    user = await service_for(InMemoryUserRepository()).create_user(
        admin_actor(),
        display_name="Ada",
        email="ada@example.com",
        is_active=True,
        phone=" +380 50 123 4567 ",
    )
    assert user.phone == "+380501234567"


async def test_create_user_rejects_a_short_phone() -> None:
    with pytest.raises(DomainValidationError, match="Phone") as caught:
        await service_for(InMemoryUserRepository()).create_user(
            admin_actor(),
            display_name="Ada",
            email="ada@example.com",
            is_active=True,
            phone="123",
        )
    assert caught.value.code == "domain_validation_error"


async def test_create_user_can_store_an_inactive_record() -> None:
    user = await service_for(InMemoryUserRepository()).create_user(
        admin_actor(),
        display_name="Ada",
        email="ada@example.com",
        is_active=False,
    )
    assert user.is_active is False


async def test_staff_password_is_stored_as_a_hash() -> None:
    user = await service_for(InMemoryUserRepository()).create_user(
        admin_actor(),
        display_name="Grace",
        email="grace@example.com",
        is_active=True,
        role="doctor",
        password="password123",
    )
    assert user.password_hash is not None
    assert user.password_hash != "password123"
    assert user.password_hash.startswith("$argon2")


async def test_patient_cannot_have_a_password() -> None:
    with pytest.raises(DomainValidationError, match="Patients"):
        await service_for(InMemoryUserRepository()).create_user(
            admin_actor(),
            display_name="Ada",
            email="ada@example.com",
            is_active=True,
            password="password123",
        )


async def test_staff_password_must_be_long_enough() -> None:
    with pytest.raises(DomainValidationError, match="Password"):
        await service_for(InMemoryUserRepository()).create_user(
            admin_actor(),
            display_name="Grace",
            email="grace@example.com",
            is_active=True,
            role="doctor",
            password="short",
        )


async def test_doctor_cannot_create_a_user() -> None:
    actor = Actor(user_id=uuid.uuid4(), role="doctor", session_id=uuid.uuid4())
    with pytest.raises(ForbiddenError) as caught:
        await service_for(InMemoryUserRepository()).create_user(
            actor,
            display_name="Ada",
            email="ada@example.com",
            is_active=True,
        )
    assert caught.value.status_code == 403


async def test_create_user_records_an_identifier_only() -> None:
    repository = InMemoryUserRepository()
    audit = RecordingAudit()
    actor = admin_actor()
    user = await service_for(repository, audit).create_user(
        actor,
        display_name="Ada",
        email="ada@example.com",
        is_active=True,
    )
    assert audit.events == [
        {
            "actor_user_id": actor.user_id,
            "action": "user.created",
            "resource_type": "user",
            "resource_id": user.id,
        }
    ]


async def test_second_administrator_bootstrap_is_closed() -> None:
    repository = InMemoryUserRepository()
    service = service_for(repository)
    await service.create_first_admin(
        display_name="Ada",
        email="ada@example.com",
        password="password123",
    )
    with pytest.raises(ConflictError) as caught:
        await service.create_first_admin(
            display_name="Grace",
            email="grace@example.com",
            password="password123",
        )
    assert caught.value.code == "bootstrap_closed"
    assert len(repository.users) == 1


@pytest.mark.parametrize(
    ("display_name", "email"),
    [
        ("   ", "ada@example.com"),
        ("A", "ada@example.com"),
        ("Ada", "not-an-email"),
        ("Ada", "ada@"),
        ("Ada", "@example.com"),
        ("Ada", "ada@example"),
        ("Ada", "a@b@example.com"),
        ("A" * 121, "ada@example.com"),
    ],
)
async def test_create_user_rejects_invalid_values(display_name: str, email: str) -> None:
    with pytest.raises(DomainValidationError) as caught:
        await service_for(InMemoryUserRepository()).create_user(
            admin_actor(),
            display_name=display_name,
            email=email,
            is_active=True,
        )
    assert caught.value.status_code == 422
    assert caught.value.code == "domain_validation_error"


async def test_create_user_rejects_duplicate_email() -> None:
    repository = InMemoryUserRepository()
    service = service_for(repository)
    await service.create_user(
        admin_actor(),
        display_name="Ada",
        email="ada@example.com",
        is_active=True,
    )

    with pytest.raises(ConflictError, match="already exists") as caught:
        await service.create_user(
            admin_actor(),
            display_name="Ada Again",
            email="ADA@example.com",
            is_active=True,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "duplicate_email"
    assert len(repository.users) == 1


async def test_create_user_translates_integrity_error_from_a_race() -> None:
    repository = InMemoryUserRepository()
    repository.raise_integrity_error = True

    with pytest.raises(ConflictError) as caught:
        await service_for(repository).create_user(
            admin_actor(),
            display_name="Ada",
            email="ada@example.com",
            is_active=True,
        )

    assert caught.value.code == "duplicate_email"
    assert repository.users == []


async def test_get_user_returns_the_stored_record() -> None:
    repository = InMemoryUserRepository()
    created = await service_for(repository).create_user(
        admin_actor(),
        display_name="Ada",
        email="ada@example.com",
        is_active=True,
    )
    found = await service_for(repository).get_user(admin_actor(), created.id)
    assert found.id == created.id


async def test_get_user_raises_for_a_missing_id() -> None:
    with pytest.raises(NotFoundError) as caught:
        await service_for(InMemoryUserRepository()).get_user(admin_actor(), uuid.uuid4())
    assert caught.value.status_code == 404
    assert caught.value.code == "user_not_found"


async def test_patient_cannot_list_users() -> None:
    actor = Actor(user_id=uuid.uuid4(), role="patient", session_id=uuid.uuid4())
    with pytest.raises(ForbiddenError):
        await service_for(InMemoryUserRepository()).list_users(actor, limit=10, offset=0)


async def test_list_users_returns_the_requested_page() -> None:
    repository = InMemoryUserRepository()
    start = datetime.now(UTC)
    repository.users = [
        make_user("one@example.com", created_at=start),
        make_user("two@example.com", created_at=start + timedelta(seconds=1)),
        make_user("three@example.com", created_at=start + timedelta(seconds=2)),
    ]

    items, total = await service_for(repository).list_users(admin_actor(), limit=2, offset=1)

    assert total == 3
    assert [item.email for item in items] == ["two@example.com", "one@example.com"]


@pytest.mark.parametrize("limit", [0, 101, -1])
async def test_list_users_rejects_limit(limit: int) -> None:
    with pytest.raises(DomainValidationError, match="Limit"):
        await service_for(InMemoryUserRepository()).list_users(admin_actor(), limit=limit, offset=0)


async def test_list_users_rejects_negative_offset() -> None:
    with pytest.raises(DomainValidationError, match="Offset"):
        await service_for(InMemoryUserRepository()).list_users(admin_actor(), limit=10, offset=-1)
