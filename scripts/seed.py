"""Insert TestCorp + one API key. Prints the raw key once; only the hash is stored."""

import asyncio
import secrets

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import ApiKey, Tenant
from app.security import hash_api_key, key_prefix

TENANT_NAME = "TestCorp"
TENANT_SLUG = "testcorp"
FREE_RPM = 60


async def seed() -> None:
    raw_key = f"sk_live_{secrets.token_urlsafe(32)}"

    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == TENANT_SLUG))
        if tenant is None:
            tenant = Tenant(name=TENANT_NAME, slug=TENANT_SLUG, rate_limit_rpm=FREE_RPM)
            session.add(tenant)
            await session.flush()

        session.add(
            ApiKey(
                tenant_id=tenant.id,
                name="free",
                key_prefix=key_prefix(raw_key),
                key_hash=hash_api_key(raw_key),
            )
        )
        await session.commit()

    await engine.dispose()

    print(f"Tenant: {TENANT_NAME} (slug={TENANT_SLUG}, plan=free, rpm={FREE_RPM})")
    print("API key (shown once; store it now):")
    print(raw_key)


if __name__ == "__main__":
    asyncio.run(seed())
