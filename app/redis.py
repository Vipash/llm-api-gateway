from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from app.config import settings

_redis: Redis | None = None


def get_redis_client() -> Redis:
    """Shared connection pool. Created on first use; closed in app lifespan."""
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def get_redis() -> AsyncGenerator[Redis, None]:
    yield get_redis_client()


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
