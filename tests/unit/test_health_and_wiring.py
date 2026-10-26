import logging
import sys

import pytest
from httpx import AsyncClient

from app.main import APP_DESCRIPTION, app
from tests.helpers import UNREACHABLE_DATABASE_URL, build_app, open_client


def test_openapi_lists_health_users_auth_and_audit() -> None:
    schema = build_app().openapi()
    paths = set(schema["paths"])
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/api/v1/users" in paths
    assert "/api/v1/users/{user_id}" in paths
    assert "/api/v1/auth/bootstrap" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/audit" in paths
    assert "server-side session" in schema["info"]["description"]
    assert schema["info"]["description"] == APP_DESCRIPTION
    user_props = schema["components"]["schemas"]["UserRead"]["properties"]
    assert "password" not in user_props
    assert "password_hash" not in user_props
    assert "role" in user_props


def test_job_libraries_are_not_imported() -> None:
    assert "redis" not in sys.modules
    assert "celery" not in sys.modules
    assert app.title == "Dental Operations Intelligence"


async def test_live_does_not_need_a_database(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unknown_route_uses_the_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "route_not_found", "message": "Not found.", "details": None}
    }


async def test_trailing_slash_is_not_redirected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "route_not_found"


async def test_ready_is_unavailable_when_the_database_refuses_connections(
    caplog: pytest.LogCaptureFixture,
) -> None:
    application = build_app(database_url=UNREACHABLE_DATABASE_URL)
    with caplog.at_level(logging.ERROR):
        async with open_client(application) as client:
            live = await client.get("/health/live")
            ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json() == {
        "status": "unavailable",
        "checks": {"database": "unavailable"},
    }
    failures = [
        record
        for record in caplog.records
        if record.getMessage() == "database readiness check failed"
    ]
    assert failures
    assert all(record.exc_info is None for record in failures)
    assert "postgresql+asyncpg://" not in caplog.text
    assert "dental:dental" not in caplog.text
