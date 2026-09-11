import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    """Verify health endpoint responds without auth."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert "status" in response.json()


@pytest.mark.asyncio
async def test_unauthorized_request_blocked():
    """Verify requests without an API key are rejected with 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_bearer_token_blocked():
    """Verify requests with a bogus Bearer token are rejected with 401."""
    headers = {"Authorization": "Bearer sk_live_completely_fake_token_12345"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 401