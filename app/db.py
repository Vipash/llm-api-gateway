from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=30,         # Keeps 20 persistent connections open
    max_overflow=20,      # Allows up to 30 temporary burst connections (50 total)
    pool_timeout=10,    # Wait up to 30s for a free connection before throwing error
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """All ORM models inherit this so Alembic can see one metadata object."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session