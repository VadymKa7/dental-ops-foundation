"""User business rules.

Emails are stored lowercase so the unique constraint does not depend on case.
A lookup rejects the common duplicate. The database constraint still rejects
two requests that pass the lookup together, and that race becomes the same
conflict error. Staff accounts store a password hash. Patients do not.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.core.actors import Actor
from app.core.exceptions import ConflictError, DomainValidationError, ForbiddenError, NotFoundError
from app.core.passwords import hash_password
from app.modules.audit.recorder import AuditRecorder
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.roles import ADMIN, ALL_ROLES, PATIENT, STAFF_ROLES

MIN_DISPLAY_NAME_LENGTH = 2
MAX_DISPLAY_NAME_LENGTH = 120
MAX_EMAIL_LENGTH = 320
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50
_FORBIDDEN = "You do not have access to this action."


def normalize_display_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise DomainValidationError("Display name cannot be blank.")
    if len(cleaned) < MIN_DISPLAY_NAME_LENGTH:
        raise DomainValidationError(
            f"Display name must be at least {MIN_DISPLAY_NAME_LENGTH} characters."
        )
    if len(cleaned) > MAX_DISPLAY_NAME_LENGTH:
        raise DomainValidationError(
            f"Display name cannot be longer than {MAX_DISPLAY_NAME_LENGTH} characters."
        )
    return cleaned


def normalize_phone(value: str | None) -> str | None:
    """Store a compact phone or nothing.

    Email stays the only identifier. A missing phone is valid. Separators are
    removed so "+380 50 123 4567" and "+380501234567" are one value.
    """
    if value is None:
        return None
    compact = "".join(character for character in value.strip() if character not in " -()")
    if not compact:
        return None
    if compact.count("+") > 1 or ("+" in compact and not compact.startswith("+")):
        raise DomainValidationError("Phone number is invalid.")
    digits = compact[1:] if compact.startswith("+") else compact
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        raise DomainValidationError("Phone number is invalid.")
    return compact


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
    def __init__(self, repository: UserRepository, audit: AuditRecorder) -> None:
        self._repository = repository
        self._audit = audit

    async def create_first_admin(
        self,
        *,
        display_name: str,
        email: str,
        password: str,
    ) -> User:
        if await self._repository.count_staff() != 0:
            raise ConflictError(
                "An administrator already exists.",
                code="bootstrap_closed",
            )
        user = await self._insert(
            display_name=display_name,
            email=email,
            is_active=True,
            phone=None,
            role=ADMIN,
            password=password,
        )
        await self._audit.record(
            actor_user_id=user.id,
            action="user.created",
            resource_type="user",
            resource_id=user.id,
        )
        return user

    async def create_user(
        self,
        actor: Actor,
        *,
        display_name: str,
        email: str,
        is_active: bool,
        phone: str | None = None,
        role: str = PATIENT,
        password: str | None = None,
    ) -> User:
        if actor.role != ADMIN:
            raise ForbiddenError(_FORBIDDEN)
        user = await self._insert(
            display_name=display_name,
            email=email,
            is_active=is_active,
            phone=phone,
            role=role,
            password=password,
        )
        await self._audit.record(
            actor_user_id=actor.user_id,
            action="user.created",
            resource_type="user",
            resource_id=user.id,
        )
        return user

    async def get_user(self, actor: Actor, user_id: uuid.UUID) -> User:
        self._require_staff(actor)
        user = await self._repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

    async def list_users(
        self,
        actor: Actor,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[User], int]:
        self._require_staff(actor)
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise DomainValidationError(f"Limit must be between 1 and {MAX_PAGE_SIZE}.")
        if offset < 0:
            raise DomainValidationError("Offset cannot be negative.")
        items = await self._repository.list_users(limit=limit, offset=offset)
        total = await self._repository.count()
        return items, total

    async def _insert(
        self,
        *,
        display_name: str,
        email: str,
        is_active: bool,
        phone: str | None,
        role: str,
        password: str | None,
    ) -> User:
        normalized_name = normalize_display_name(display_name)
        normalized_email = normalize_email(email)
        normalized_phone = normalize_phone(phone)
        password_hash = await self._password_hash_for(role, password)
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
            phone=normalized_phone,
            role=role,
            password_hash=password_hash,
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

    async def _password_hash_for(self, role: str, password: str | None) -> str | None:
        if role not in ALL_ROLES:
            raise DomainValidationError("Role is invalid.")
        if role == PATIENT:
            if password is not None:
                raise DomainValidationError("Patients cannot have a password.")
            return None
        password_length = 0 if password is None else len(password)
        if password is None or not MIN_PASSWORD_LENGTH <= password_length <= MAX_PASSWORD_LENGTH:
            raise DomainValidationError(
                "Password must be between "
                f"{MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters."
            )
        return await asyncio.to_thread(hash_password, password)

    def _require_staff(self, actor: Actor) -> None:
        if actor.role not in STAFF_ROLES:
            raise ForbiddenError(_FORBIDDEN)
