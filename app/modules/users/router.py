"""User HTTP routes.

Creating an account requires an administrator. Reading the directory requires
any staff session. Patients have no password and cannot sign in.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_actor, get_user_service
from app.api.errors import ErrorResponse
from app.core.actors import Actor
from app.modules.users.schemas import UserCreate, UserListResponse, UserRead
from app.modules.users.service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, UserService

router = APIRouter(tags=["users"])


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Create a user",
)
async def create_user(
    actor: Annotated[Actor, Depends(get_actor)],
    payload: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    user = await service.create_user(
        actor,
        display_name=payload.display_name,
        email=str(payload.email),
        is_active=payload.is_active,
        phone=payload.phone,
        role=payload.role,
        password=payload.password,
    )
    return UserRead.model_validate(user)


@router.get(
    "/users",
    response_model=UserListResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="List users",
)
async def list_users(
    actor: Annotated[Actor, Depends(get_actor)],
    service: Annotated[UserService, Depends(get_user_service)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListResponse:
    items, total = await service.list_users(actor, limit=limit, offset=offset)
    return UserListResponse(
        items=[UserRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/users/{user_id}",
    response_model=UserRead,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Get a user",
)
async def get_user(
    actor: Annotated[Actor, Depends(get_actor)],
    user_id: UUID,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    user = await service.get_user(actor, user_id)
    return UserRead.model_validate(user)
