"""ASGI entrypoint.

`create_app` is the composition root. Tests pass Settings explicitly.
Uvicorn imports the module-level `app`, which reads the process environment.
Health routes stay on the root. Business routes use `api_prefix`.
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import (
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.api.health import router as health_router
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.db.session import create_db_engine, create_session_factory

APP_DESCRIPTION = (
    "Dental Operations Intelligence backend foundation. "
    "Staff sign in with a server-side session. Patients have no password and cannot sign in. "
    "Do not deploy this service with real patient or customer data until production hardening."
)

access_logger = logging.getLogger("app.access")


class AccessLogMiddleware:
    """Log method, path, status, and duration. Query strings and bodies are omitted."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = str(scope.get("path", ""))[:200]
            access_logger.info(
                "request completed",
                extra={
                    "http_method": str(scope.get("method", "")),
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the engine for the process and dispose it on shutdown."""
    settings = cast(Settings, app.state.settings)
    configure_logging(settings.log_level)
    engine = create_db_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application.

    Tests pass a Settings instance so they do not depend on a developer's .env file.
    """
    resolved = settings if settings is not None else get_settings()
    configure_logging(resolved.log_level)
    application = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        description=APP_DESCRIPTION,
        lifespan=lifespan,
        debug=resolved.debug,
        redirect_slashes=False,
    )
    application.state.settings = resolved
    application.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,  # type: ignore[arg-type]
    )
    application.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,  # type: ignore[arg-type]
    )
    application.add_exception_handler(Exception, unhandled_exception_handler)
    application.add_middleware(AccessLogMiddleware)
    application.include_router(health_router)
    application.include_router(api_router, prefix=resolved.api_prefix)
    return application


app = create_app()
