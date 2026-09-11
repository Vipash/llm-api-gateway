import pytest
import pytest_asyncio
import fakeredis.aioredis
from unittest.mock import patch


@pytest_asyncio.fixture(autouse=True)
async def mock_redis_server():
    """Globally patch Redis client with an in-memory FakeServer for unit tests."""
    fake_redis = fakeredis.aioredis.FakeRedis()
    with patch("app.redis._redis", fake_redis):
        yield fake_redis
    await fake_redis.aclose()