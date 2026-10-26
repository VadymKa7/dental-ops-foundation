"""Audit HTTP routes. Reading the trail is limited to an administrator."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_actor, get_audit_service
from app.api.errors import ErrorResponse
from app.core.actors import Actor
from app.modules.audit.schemas import AuditEventRead
from app.modules.audit.service import MAX_PAGE_SIZE, AuditService

router = APIRouter(tags=["audit"])


@router.get(
    "/audit",
    response_model=list[AuditEventRead],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    summary="List audit events",
)
async def list_audit_events(
    actor: Annotated[Actor, Depends(get_actor)],
    service: Annotated[AuditService, Depends(get_audit_service)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> list[AuditEventRead]:
    events = await service.list_events(actor, limit=limit)
    return [AuditEventRead.model_validate(event) for event in events]
