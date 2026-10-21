"""Map domain and request errors onto one JSON envelope."""

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.logging import log_failure

logger = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    loc: list[str]
    msg: str
    type: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    del request
    return error_response(status_code=exc.status_code, code=exc.code, message=exc.message)


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    del request
    details = [
        ErrorDetail(
            loc=[str(part) for part in item.get("loc", ())],
            msg=str(item.get("msg", "Invalid value.")),
            type=str(item.get("type", "value_error")),
        )
        for item in exc.errors()
    ]
    return error_response(
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
        details=details,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    del request
    if exc.status_code == 404:
        code = "route_not_found"
        message = "Not found."
    elif exc.status_code == 405:
        code = "method_not_allowed"
        message = "Method not allowed."
    else:
        code = "http_error"
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return error_response(status_code=exc.status_code, code=code, message=message)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    del request
    log_failure(logger, "unhandled request error", exc)
    return error_response(
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred.",
    )
