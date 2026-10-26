"""Audit port used by other services."""

import uuid
from typing import Protocol


class AuditRecorder(Protocol):
    async def record(
        self,
        *,
        actor_user_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> None: ...
