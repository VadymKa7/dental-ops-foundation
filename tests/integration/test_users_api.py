import uuid

import pytest
from httpx import AsyncClient

from tests.helpers import bearer, bootstrap_admin

pytestmark = pytest.mark.integration


async def test_create_get_and_list_users(client: AsyncClient) -> None:
    anonymous = await client.get("/api/v1/users")
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "authentication_required"

    token = await bootstrap_admin(client)
    headers = bearer(token)

    created = await client.post(
        "/api/v1/users",
        headers=headers,
        json={"display_name": "  Ada Lovelace  ", "email": "  Ada@Example.com "},
    )
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {
        "id",
        "display_name",
        "email",
        "phone",
        "role",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert "password" not in body
    assert "password_hash" not in body
    assert body["display_name"] == "Ada Lovelace"
    assert body["email"] == "ada@example.com"
    assert body["phone"] is None
    assert body["role"] == "patient"
    assert body["is_active"] is True
    assert body["created_at"] == body["updated_at"]
    assert body["created_at"].endswith("+00:00") or body["created_at"].endswith("Z")
    user_id = body["id"]
    uuid.UUID(user_id)

    fetched = await client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json() == body

    listed = await client.get("/api/v1/users", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 2
    assert body in payload["items"]


async def test_inactive_user_is_stored_and_returned(client: AsyncClient) -> None:
    headers = bearer(await bootstrap_admin(client))
    created = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "display_name": "Grace",
            "email": "grace@example.com",
            "is_active": False,
        },
    )
    assert created.status_code == 201
    assert created.json()["is_active"] is False

    fetched = await client.get(f"/api/v1/users/{created.json()['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["is_active"] is False


async def test_duplicate_email_is_a_conflict_including_case_variants(client: AsyncClient) -> None:
    headers = bearer(await bootstrap_admin(client))
    first = await client.post(
        "/api/v1/users",
        headers=headers,
        json={"display_name": "Ada", "email": "ada@example.com"},
    )
    assert first.status_code == 201

    duplicate = await client.post(
        "/api/v1/users",
        headers=headers,
        json={"display_name": "Ada Again", "email": "ADA@example.com"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_email"

    listed = await client.get("/api/v1/users", headers=headers)
    assert listed.json()["total"] == 2


async def test_missing_user_returns_404(client: AsyncClient) -> None:
    anonymous = await client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert anonymous.status_code == 401

    headers = bearer(await bootstrap_admin(client))
    response = await client.get(f"/api/v1/users/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "user_not_found", "message": "User not found.", "details": None}
    }


async def test_invalid_user_id_returns_validation_error(client: AsyncClient) -> None:
    headers = bearer(await bootstrap_admin(client))
    response = await client.get("/api/v1/users/not-a-uuid", headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": "   ", "email": "ada@example.com"},
        {"display_name": "A", "email": "ada@example.com"},
        {"display_name": "Ada", "email": "ada@example.com", "phone": "123"},
        {"display_name": "Ada", "email": "not-an-email"},
        {"email": "ada@example.com"},
        {"display_name": "Ada", "email": "ada@example.com", "password": "secret"},
        {"display_name": "Ada", "email": "ada@example.com", "role": "doctor"},
    ],
)
async def test_invalid_create_payloads_use_the_error_envelope(
    client: AsyncClient,
    payload: dict[str, str],
) -> None:
    headers = bearer(await bootstrap_admin(client))
    response = await client.post("/api/v1/users", headers=headers, json=payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]
    rendered = response.text
    assert "secret" not in rendered
    assert "password123" not in rendered


async def test_invalid_page_size_is_rejected(client: AsyncClient) -> None:
    headers = bearer(await bootstrap_admin(client))
    response = await client.get("/api/v1/users", headers=headers, params={"limit": 0})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_list_pagination_reports_the_full_total(client: AsyncClient) -> None:
    headers = bearer(await bootstrap_admin(client))
    for name, email in (("Ada", "ada@example.com"), ("Grace", "grace@example.com")):
        created = await client.post(
            "/api/v1/users",
            headers=headers,
            json={"display_name": name, "email": email},
        )
        assert created.status_code == 201

    page = await client.get("/api/v1/users", headers=headers, params={"limit": 1, "offset": 0})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert len(body["items"]) == 1

    full = await client.get("/api/v1/users", headers=headers, params={"limit": 3, "offset": 0})
    created_at = [item["created_at"] for item in full.json()["items"]]
    assert created_at == sorted(created_at, reverse=True)
    assert len(created_at) == 3
