import pytest
from httpx import AsyncClient

from tests.helpers import bearer, bootstrap_admin

pytestmark = pytest.mark.integration


async def test_staff_login_logout_and_role_boundaries(client: AsyncClient) -> None:
    admin_token = await bootstrap_admin(client)
    created = await client.post(
        "/api/v1/users",
        headers=bearer(admin_token),
        json={
            "display_name": "Grace",
            "email": "grace@example.com",
            "role": "doctor",
            "password": "password123",
        },
    )
    assert created.status_code == 201
    assert created.json()["role"] == "doctor"
    assert "password_hash" not in created.json()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "Grace@Example.com", "password": "password123"},
    )
    assert login.status_code == 200
    doctor_token = login.json()["access_token"]
    assert login.json()["user"]["role"] == "doctor"

    denied = await client.post(
        "/api/v1/users",
        headers=bearer(doctor_token),
        json={"display_name": "Pat", "email": "pat@example.com"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"

    listed = await client.get("/api/v1/users", headers=bearer(doctor_token))
    assert listed.status_code == 200

    hidden = await client.get("/api/v1/audit", headers=bearer(doctor_token))
    assert hidden.status_code == 403

    trail = await client.get("/api/v1/audit", headers=bearer(admin_token))
    assert trail.status_code == 200
    rendered = trail.text
    assert "password123" not in rendered
    assert "grace@example.com" not in rendered
    assert "user.created" in rendered
    assert "session.created" in rendered

    logged_out = await client.post("/api/v1/auth/logout", headers=bearer(doctor_token))
    assert logged_out.status_code == 204
    reused = await client.get("/api/v1/users", headers=bearer(doctor_token))
    assert reused.status_code == 401


async def test_login_failures_and_closed_bootstrap(client: AsyncClient) -> None:
    await bootstrap_admin(client, email="admin@example.com")
    again = await client.post(
        "/api/v1/auth/bootstrap",
        json={
            "display_name": "Other Admin",
            "email": "other@example.com",
            "password": "password123",
        },
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "bootstrap_closed"

    patient = await client.post(
        "/api/v1/users",
        headers=bearer(await _login(client, "admin@example.com")),
        json={"display_name": "Pat", "email": "pat@example.com"},
    )
    assert patient.status_code == 201

    wrong = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )
    missing = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "password123"},
    )
    patient_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "pat@example.com", "password": "password123"},
    )
    assert wrong.status_code == missing.status_code == patient_login.status_code == 401
    assert wrong.json() == missing.json() == patient_login.json()
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert "password123" not in wrong.text


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert isinstance(token, str)
    return token
