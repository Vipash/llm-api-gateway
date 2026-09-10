Markdown

```
# Multi-Tenant LLM API Gateway

A high-performance, observable API gateway built with FastAPI (async), PostgreSQL, and Redis that proxies, rate limits, and observes traffic to LLM backends (Ollama / OpenAI).

Designed for production AI infrastructure: features atomic sliding-window rate limiting, read-through authentication caching, native Server-Sent Events (SSE) streaming, non-blocking telemetry logging, and Prometheus/Grafana observability.

---

## Architecture Overview

```text
[ Client / k6 Load Generator ]  
       │  
       │ Bearer Token | HTTP POST /v1/chat/completions (stream: true|false)  
       ▼  
┌──────────────────────────────────────────────────────────┐  
│                      FastAPI Gateway                     │  
└──────────────┬────────────────────────────┬──────────────┘  
               │                            │  
  1. Auth Check│ (Read-Through Cache)       │ 2. Rate Limiting (Atomic Lua)  
               ▼                            ▼  
    ┌─────────────────┐          ┌─────────────────┐  
    │      Redis      │          │   Redis (ZSET)  │  
    │  cache:auth:*   │          │  rate_limit:*   │  
    └────────┬────────┘          └────────┬────────┘  
             │ Miss                       │ Allowed: Inject headers  
             ▼                            │ Exceeded: 429 Too Many Requests  
    ┌─────────────────┐                   ▼  
    │   PostgreSQL    │          ┌───────────────────────────────────┐  
    │   (api_keys)    │          │ Upstream Client (Ollama / Mock)   │  
    └─────────────────┘          │ • Buffered JSON OR                │  
                                 │ • SSE Real-Time Stream            │  
                                 └────────────────┬──────────────────┘  
                                                  │  
                                                  ▼  
                                 ┌───────────────────────────────────┐  
                                 │      FastAPI BackgroundTasks      │  
                                 └────────────────┬──────────────────┘  
                                                  │ Non-blocking async write  
                                                  ▼  
                                 ┌───────────────────────────────────┐  
                                 │            PostgreSQL             │  
                                 │ • request_logs                    │  
                                 │ • daily_usage                     │  
                                 └───────────────────────────────────┘  

[ Scrape /metrics (5s) ] ──► [ Prometheus:9090 ] ──► [ Grafana:3000 ]

```

## Key Engineering Features

- **Multi-Tenant Auth & Read-Through Caching:** API keys are hashed with SHA-256 (raw keys are never stored). Validated tenants are cached in Redis with a 300s TTL, eliminating redundant database connection checkouts.
- **Atomic Sliding-Window Rate Limiter:** Built using Redis Sorted Sets (`ZSET`) and evaluated via a custom **Lua script** (`EVAL`) to guarantee atomicity and prevent check-then-act race conditions across concurrent workers. Returns `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `Retry-After` headers.
- **Dual Execution Engine (Buffered & SSE Streaming):** Supports standard OpenAI-compatible requests (`POST /v1/chat/completions`) with real-time token streaming via Server-Sent Events (`text/event-stream`), measuring Time-To-First-Token (TTFT).
- **Non-Blocking Telemetry:** Request latency, prompt/completion tokens, and daily aggregates are offloaded to PostgreSQL using FastAPI `BackgroundTasks`, isolating analytical persistence from the client latency path.
- **Full Observability Stack:** Custom Prometheus metrics (`llm_gateway_requests_total`, `llm_gateway_tokens_total`, `llm_gateway_request_duration_seconds`) scraped every 5s and visualized in real-time Grafana dashboards.

## Performance & Load Test Benchmarks

Load tested using **k6** simulating sustained concurrent traffic against a 50ms mock upstream:

  



|                                |                                              |                                           |                 |
| ------------------------------ | -------------------------------------------- | ----------------------------------------- | --------------- |
| **Metric**                     | **Before Optimization (DB Auth Bottleneck)** | **After Optimization (Redis Auth Cache)** | **Improvement** |
| **Throughput (RPS)**           | 11.7 req/s                                   | **70.0 req/s**                            | **6x Increase** |
| **Median Latency (**`med`**)** | 2,280 ms                                     | **129 ms**                                | **17x Faster**  |
| **P90 Latency**                | 5,990 ms                                     | **248 ms**                                | **24x Faster**  |
| **P95 Latency**                | 7,030 ms                                     | **302 ms**                                | **23x Faster**  |
| **Success Rate**               | 99.15% (socket dropouts)                     | **100.00% (0 errors / 2,106 reqs)**       | **Zero Drops**  |


> **Key Architectural Takeaway:** Moving tenant validation from an inline database query to a read-through Redis cache dropped connection checkout contention by 50% and eliminated lock contention on daily rollup rows during high-concurrency bursts.
>
>

## Tech Stack

- **Application:** Python 3.12, FastAPI (async), Uvicorn, Pydantic Settings
- **Package Management:** `uv`
- **Database & Migrations:** PostgreSQL 16, SQLAlchemy 2.0 (asyncpg), Alembic
- **Caching & Rate Limiting:** Redis 7 (`redis-py` async + Lua scripting)
- **Observability:** Prometheus, Grafana, `prometheus_client`
- **Benchmarking:** k6

## Quickstart (Local Run)

### 1. Prerequisites

- [uv](https://docs.astral.sh/uv/)
- [Docker Desktop](https://www.docker.com/)
- (Optional) [Ollama](https://ollama.com/) with `qwen2.5-coder:1.5b` installed

### 2. Environment & Infrastructure Setup

PowerShell

```
# Clone and enter repo
cd llm-gateway

# Set up environment variables
copy .env.example .env

# Start Postgres, Redis, Prometheus, and Grafana
docker compose up -d

# Sync dependencies and run DB migrations
uv sync --group dev
uv run alembic upgrade head

# Seed test tenant and generate an API key
uv run python -m scripts.seed
# (Save the printed sk_live_... key!)

```

### 3. Run Gateway

PowerShell

```
uv run uvicorn app.main:app --reload

```

- **Interactive API Docs (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus UI:** [http://localhost:9090](http://localhost:9090)
- **Grafana Dashboard:** [http://localhost:3000](http://localhost:3000) (admin/admin)

## API Usage Examples

### 1. Buffered Request

PowerShell

```
$headers = @{
    "Authorization" = "Bearer sk_live_YOUR_KEY"
    "Content-Type" = "application/json"
}
$body = '{"model":"qwen2.5-coder:1.5b","messages":[{"role":"user","content":"ping"}]}'

Invoke-RestMethod -Uri "http://localhost:8000/v1/chat/completions" -Method Post -Headers $headers -Body $body

```

### 2. Real-Time Streaming (SSE)

PowerShell

```
curl.exe -N -X POST "http://localhost:8000/v1/chat/completions" `
  -H "Authorization: Bearer sk_live_YOUR_KEY" `
  -H "Content-Type: application/json" `
  -d '{"model":"qwen2.5-coder:1.5b","messages":[{"role":"user","content":"Count 1 to 5"}],"stream":true}'

```

## Running Benchmarks

PowerShell

```
# Set MOCK_UPSTREAM=true in .env to isolate gateway performance from local GPU speed
k6 run tests/load/benchmark.js
```

