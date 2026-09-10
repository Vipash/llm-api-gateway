# LLM Gateway

Multi-tenant LLM API gateway: FastAPI proxies `POST /v1/chat/completions` to a local Ollama (OpenAI-compatible) endpoint, with tenant API keys, Postgres usage data, and Redis rate limiting to be layered on next.

## Tech stack

- Python 3.12+, FastAPI (async), `uv` for deps/venv
- PostgreSQL via SQLAlchemy 2.0 async + Alembic
- Redis (rate limiting / cache — not wired yet)
- Docker Compose for Postgres + Redis

## Architecture

```
Client  --Bearer sk_live_...-->  FastAPI (/v1/chat/completions)
                                  |  hash lookup → Tenant
                                  |  Redis RPM (later)
                                  v
                            httpx proxy
                                  |
                                  v
                         Ollama :11434/v1
                    (or OpenAI later via env)

Postgres: tenants, hashed api_keys, request_logs, daily_usage
Redis:    per-tenant rate limits (next phase)
```

## Local run

**Prereqs:** [uv](https://docs.astral.sh/uv/), Docker Desktop, and (for the proxy) [Ollama](https://ollama.com/) with a pulled model.

```powershell
cd ~\llm-gateway
copy .env.example .env

docker compose up -d
uv sync --group dev
uv run alembic upgrade head
uv run python scripts/seed.py
uv run uvicorn app.main:app --reload
```

- API + Swagger: http://localhost:8000/docs
- Health: `GET http://localhost:8000/health`

Chat request (Ollama must be running; use the key printed by seed):

```powershell
curl http://localhost:8000/v1/chat/completions -H "Authorization: Bearer sk_live_YOUR_KEY" -H "Content-Type: application/json" -d "{\"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}"
```

Tests:

```powershell
uv run pytest
```

## Important patterns (for later phases)

- **Hashed keys:** `app/security.py` SHA-256 hashes raw keys. DB stores `key_hash` + `key_prefix` only. Lookup is `hash(incoming)` then match `key_hash` — never store the secret.
- **Settings:** `app/config.py` is a `pydantic-settings` singleton. Add env vars there, not `os.getenv` scattered around.
- **Async DB:** `get_db` yields an `AsyncSession`. Use `Depends(get_db)` on routes that need Postgres.
- **Alembic is async:** `alembic/env.py` uses `create_async_engine` so `DATABASE_URL` stays `postgresql+asyncpg://...`. Keep revisions linear (`down_revision` points at the previous id).

## Suggested next phases

1. Per-tenant Redis rate limiting using `tenants.rate_limit_rpm`
2. Write `request_logs` + upsert `daily_usage` after each proxy call
3. OpenTelemetry → Prometheus + Jaeger/Tempo + Grafana in Compose
