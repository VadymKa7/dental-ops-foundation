from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from tests.helpers import build_app, open_client


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    application = build_app()
    async with open_client(application) as http:
        yield http
