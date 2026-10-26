"""Sign-in HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_actor, get_auth_service
from app.api.errors import ErrorResponse
from app.core.actors import Actor
from app.modules.auth.schemas import BootstrapRequest, LoginRead, LoginRequest
from app.modules.auth.service import AuthService, LoginResult
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _login_response(result: LoginResult) -> LoginRead:
    return LoginRead(
        access_token=result.access_token,
        expires_at=result.expires_at,
        user=UserRead.model_validate(result.user),
    )


@router.post(
    "/bootstrap",
    response_model=LoginRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Create the first administrator",
    description="Open only while no staff account exists. Later accounts are created by an admin.",
)
async def bootstrap_admin(
    payload: BootstrapRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginRead:
    result = await service.bootstrap_admin(
        display_name=payload.display_name,
        email=str(payload.email),
        password=payload.password,
    )
    return _login_response(result)


@router.post(
    "/login",
    response_model=LoginRead,
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Sign in",
)
async def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginRead:
    result = await service.login(email=str(payload.email), password=payload.password)
    return _login_response(result)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}},
    summary="Revoke the current session",
)
async def logout(
    actor: Annotated[Actor, Depends(get_actor)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    await service.logout(actor)
