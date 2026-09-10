import asyncio
import hashlib
from sqlalchemy import select
from app.db import AsyncSession, engine
from app.models import Tenant, ApiKey

async def seed():
    async with AsyncSession(bind=engine) as session:
        # 1. Check if the tenant already exists
        stmt = select(Tenant).where(Tenant.slug == "test-tenant")
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

        if not tenant:
            # Create Tenant if missing
            tenant = Tenant(name="Test Tenant", slug="test-tenant")
            session.add(tenant)
            await session.flush()

            raw_key = "sk_live_tFFN_m8pza1qGUnaoQtHCUo3WqAt6fmXi-Qwkjz4kUA"
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

            api_key = ApiKey(
                tenant_id=tenant.id,
                key_prefix="sk_live_tFFN",
                key_hash=key_hash,
                name="Development Key"
            )
            session.add(api_key)
            await session.commit()
            print("Successfully seeded Tenant and API Key!")
        else:
            print("Database already seeded: 'test-tenant' exists.")

if __name__ == "__main__":
    asyncio.run(seed())