from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.redis import close_redis
from app.routers import chat, health


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_redis()


app = FastAPI(
    title="LLM Gateway",
    description="Multi-tenant LLM API gateway. Use /docs to try endpoints.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(chat.router)

# Initialize and expose Prometheus metrics endpoint at /metrics
Instrumentator().instrument(app).expose(app)