"""User HTTP routes.

Authentication is not implemented. These routes are a technical example.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.errors import ErrorResponse
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate, UserListResponse, UserRead
from app.modules.users.service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, UserService

_UNAUTHENTICATED = (
    "Authentication is not implemented. This is a technical example, not an account API."
)

router = APIRouter(tags=["users"])


def get_user_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserService:
    return UserService(UserRepository(session))


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Create a user",
    description=_UNAUTHENTICATED,
)
async def create_user(
    payload: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    user = await service.create_user(
        display_name=payload.display_name,
        email=str(payload.email),
        is_active=payload.is_active,
    )
    return UserRead.model_validate(user)


@router.get(
    "/users",
    response_model=UserListResponse,
    responses={422: {"model": ErrorResponse}},
    summary="List users",
    description=_UNAUTHENTICATED,
)
async def list_users(
    service: Annotated[UserService, Depends(get_user_service)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListResponse:
    items, total = await service.list_users(limit=limit, offset=offset)
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
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Get a user",
    description=_UNAUTHENTICATED,
)
async def get_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserRead:
    user = await service.get_user(user_id)
    return UserRead.model_validate(user)
