import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
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


def service_for(repository: InMemoryUserRepository) -> UserService:
    return UserService(cast(UserRepository, repository))


def make_user(email: str, *, created_at: datetime | None = None) -> User:
    timestamp = created_at or datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        display_name="Ada",
        email=email,
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )


async def test_create_user_normalizes_name_and_email() -> None:
    repository = InMemoryUserRepository()
    user = await service_for(repository).create_user(
        display_name="  Ada Lovelace  ",
        email="  Ada@Example.com ",
        is_active=True,
    )

    assert user.display_name == "Ada Lovelace"
    assert user.email == "ada@example.com"
    assert user.is_active is True
    assert user.created_at == user.updated_at
    assert repository.users == [user]


async def test_create_user_can_store_an_inactive_record() -> None:
    user = await service_for(InMemoryUserRepository()).create_user(
        display_name="Ada",
        email="ada@example.com",
        is_active=False,
    )
    assert user.is_active is False


@pytest.mark.parametrize(
    ("display_name", "email"),
    [
        ("   ", "ada@example.com"),
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
            display_name=display_name,
            email=email,
            is_active=True,
        )
    assert caught.value.status_code == 422
    assert caught.value.code == "domain_validation_error"


async def test_create_user_rejects_duplicate_email() -> None:
    repository = InMemoryUserRepository()
    service = service_for(repository)
    await service.create_user(display_name="Ada", email="ada@example.com", is_active=True)

    with pytest.raises(ConflictError, match="already exists") as caught:
        await service.create_user(display_name="Ada Again", email="ADA@example.com", is_active=True)

    assert caught.value.status_code == 409
    assert caught.value.code == "duplicate_email"
    assert len(repository.users) == 1


async def test_create_user_translates_integrity_error_from_a_race() -> None:
    repository = InMemoryUserRepository()
    repository.raise_integrity_error = True

    with pytest.raises(ConflictError) as caught:
        await service_for(repository).create_user(
            display_name="Ada",
            email="ada@example.com",
            is_active=True,
        )

    assert caught.value.code == "duplicate_email"
    assert repository.users == []


async def test_get_user_returns_the_stored_record() -> None:
    repository = InMemoryUserRepository()
    created = await service_for(repository).create_user(
        display_name="Ada",
        email="ada@example.com",
        is_active=True,
    )
    found = await service_for(repository).get_user(created.id)
    assert found.id == created.id


async def test_get_user_raises_for_a_missing_id() -> None:
    with pytest.raises(NotFoundError) as caught:
        await service_for(InMemoryUserRepository()).get_user(uuid.uuid4())
    assert caught.value.status_code == 404
    assert caught.value.code == "user_not_found"


async def test_list_users_returns_the_requested_page() -> None:
    repository = InMemoryUserRepository()
    start = datetime.now(UTC)
    repository.users = [
        make_user("one@example.com", created_at=start),
        make_user("two@example.com", created_at=start + timedelta(seconds=1)),
        make_user("three@example.com", created_at=start + timedelta(seconds=2)),
    ]

    items, total = await service_for(repository).list_users(limit=2, offset=1)

    assert total == 3
    assert [item.email for item in items] == ["two@example.com", "one@example.com"]


@pytest.mark.parametrize("limit", [0, 101, -1])
async def test_list_users_rejects_limit(limit: int) -> None:
    with pytest.raises(DomainValidationError, match="Limit"):
        await service_for(InMemoryUserRepository()).list_users(limit=limit, offset=0)


async def test_list_users_rejects_negative_offset() -> None:
    with pytest.raises(DomainValidationError, match="Offset"):
        await service_for(InMemoryUserRepository()).list_users(limit=10, offset=-1)
