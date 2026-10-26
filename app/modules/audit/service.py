"""Audit rules.

The stored fields are identifiers. Callers choose the action name. This
service does not accept a free-form payload, because that payload would be
where a password or email would leak.
"""

import uuid
from datetime import UTC, datetime

from app.core.actors import Actor
from app.core.exceptions import DomainValidationError, ForbiddenError
from app.modules.audit.models import AuditEvent
from app.modules.audit.repository import AuditRepository
from app.modules.users.roles import ADMIN

MAX_PAGE_SIZE = 100


class AuditService:
    def __init__(self, repository: AuditRepository) -> None:
        self._repository = repository

    async def record(
        self,
        *,
        actor_user_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> None:
        event = AuditEvent(
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            created_at=datetime.now(UTC),
        )
        await self._repository.add(event)

    async def list_events(self, actor: Actor, *, limit: int) -> list[AuditEvent]:
        if actor.role != ADMIN:
            raise ForbiddenError("You do not have access to this action.")
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise DomainValidationError(f"Limit must be between 1 and {MAX_PAGE_SIZE}.")
        return await self._repository.list_events(limit=limit)
