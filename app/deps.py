import json
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import LLM_RATE_LIMIT_EXCEEDED_TOTAL
from app.db import get_db
from app.models import ApiKey, Tenant
from app.redis import get_redis
from app.security import hash_api_key
from app.services.rate_limiter import is_rate_limited

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_tenant(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Tenant:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    key_hash = hash_api_key(creds.credentials)
    cache_key = f"cache:auth:{key_hash}"

    # 1. Fast path: Check Redis cache
    cached_data = await redis.get(cache_key)
    if cached_data:
        data = json.loads(cached_data)
        return Tenant(
            id=uuid.UUID(data["id"]) if isinstance(data["id"], str) else data["id"],
            name=data["name"],
            slug=data["slug"],
            rate_limit_rpm=data["rate_limit_rpm"],
        )

    # 2. Slow path: Query PostgreSQL
    result = await db.execute(
        select(Tenant)
        .join(ApiKey)
        .where(
            ApiKey.key_hash == key_hash,
            ApiKey.revoked_at.is_(None),
        )
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    # 3. Cache tenant metadata in Redis for 300 seconds
    tenant_payload = {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "rate_limit_rpm": tenant.rate_limit_rpm,
    }
    await redis.setex(cache_key, 300, json.dumps(tenant_payload))

    return tenant


async def rate_limit_check(
    request: Request,
    response: Response,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    limit = getattr(tenant, "rate_limit_rpm", None) or 60
    allowed, remaining, reset_seconds = await is_rate_limited(
        redis,
        str(tenant.id),
        limit,
        window_seconds=60,
    )

    if not allowed:
        LLM_RATE_LIMIT_EXCEEDED_TOTAL.labels(tenant_id=str(tenant.id)).inc()

        headers = {
            "Retry-After": str(reset_seconds),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(reset_seconds),
        }
        request.state.rate_limit_headers = headers
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=headers,
        )

    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_seconds)

    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(reset_seconds),
    }