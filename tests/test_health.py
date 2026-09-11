import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security import hash_api_key


@pytest.mark.asyncio
async def test_health() -> None:
    """Verify health endpoint responds without auth using AsyncClient."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_hash_api_key_is_sha256_hex() -> None:
    """Verify SHA-256 API key hashing logic."""
    digest = hash_api_key("sk_example")
    assert len(digest) == 64
    assert digest == hash_api_key("sk_example")
    assert digest != hash_api_key("sk_other")