"""User business rules.

Emails are stored lowercase so the unique constraint does not depend on case.
A lookup rejects the common duplicate. The database constraint still rejects
two requests that pass the lookup together, and that race becomes the same
conflict error. This module does not authenticate callers.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

MAX_DISPLAY_NAME_LENGTH = 120
MAX_EMAIL_LENGTH = 320
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


def normalize_display_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise DomainValidationError("Display name cannot be blank.")
    if len(cleaned) > MAX_DISPLAY_NAME_LENGTH:
        raise DomainValidationError(
            f"Display name cannot be longer than {MAX_DISPLAY_NAME_LENGTH} characters."
        )
    return cleaned


def normalize_email(value: str) -> str:
    cleaned = value.strip().lower()
    local, separator, domain = cleaned.partition("@")
    domain_labels = domain.split(".")
    if (
        len(cleaned) > MAX_EMAIL_LENGTH
        or separator != "@"
        or "@" in domain
        or not local
        or len(domain_labels) < 2
        or any(not label for label in domain_labels)
        or any(character.isspace() for character in cleaned)
    ):
        raise DomainValidationError("Email is invalid.")
    return cleaned


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def create_user(self, *, display_name: str, email: str, is_active: bool) -> User:
        normalized_name = normalize_display_name(display_name)
        normalized_email = normalize_email(email)
        existing = await self._repository.get_by_email(normalized_email)
        if existing is not None:
            raise ConflictError(
                "A user with this email already exists.",
                code="duplicate_email",
            )
        now = datetime.now(UTC)
        user = User(
            id=uuid.uuid4(),
            display_name=normalized_name,
            email=normalized_email,
            is_active=is_active,
            created_at=now,
            updated_at=now,
        )
        try:
            return await self._repository.add(user)
        except IntegrityError as exc:
            raise ConflictError(
                "A user with this email already exists.",
                code="duplicate_email",
            ) from exc

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self._repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

    async def list_users(self, *, limit: int, offset: int) -> tuple[list[User], int]:
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise DomainValidationError(f"Limit must be between 1 and {MAX_PAGE_SIZE}.")
        if offset < 0:
            raise DomainValidationError("Offset cannot be negative.")
        items = await self._repository.list_users(limit=limit, offset=offset)
        total = await self._repository.count()
        return items, total
