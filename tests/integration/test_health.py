import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_live_and_ready_against_postgres(client: AsyncClient) -> None:
    live = await client.get("/health/live")
    ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "checks": {"database": "ok"}}
