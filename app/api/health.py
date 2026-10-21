"""Liveness and readiness probes.

These routes are mounted at the application root, outside /api/v1, so process
probes do not depend on the business API version. Readiness checks that the
database accepts a connection. It does not check that migrations are current.
"""

import logging
from typing import Literal, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class LiveStatus(BaseModel):
    status: Literal["ok"]


class ReadyStatus(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: dict[str, Literal["ok", "unavailable"]]


@router.get("/health/live", response_model=LiveStatus, summary="Process liveness")
async def live() -> LiveStatus:
    return LiveStatus(status="ok")


@router.get(
    "/health/ready",
    response_model=ReadyStatus,
    responses={503: {"model": ReadyStatus}},
    summary="Database readiness",
)
async def ready(request: Request) -> ReadyStatus | JSONResponse:
    engine = cast(AsyncEngine, request.app.state.engine)
    if await database_is_ready(engine):
        return ReadyStatus(status="ok", checks={"database": "ok"})
    body = ReadyStatus(status="unavailable", checks={"database": "unavailable"})
    return JSONResponse(status_code=503, content=body.model_dump(mode="json"))


async def database_is_ready(engine: AsyncEngine) -> bool:
    """Return whether `SELECT 1` succeeds.

    Any driver failure means not ready. The exception text is not logged,
    because it can contain the database URL.
    """
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error(
            "database readiness check failed",
            extra={"error_type": exc.__class__.__name__},
        )
        return False
    return True
