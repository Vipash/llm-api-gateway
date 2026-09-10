from prometheus_client import Counter, Histogram

# 1. Total chat requests partitioned by tenant, model, and final HTTP status
LLM_REQUESTS_TOTAL = Counter(
    "llm_gateway_requests_total",
    "Total LLM completion requests processed",
    ["tenant_id", "model", "status_code"],
)

# 2. Token counter partitioned by tenant, model, and token type (prompt vs completion)
LLM_TOKENS_TOTAL = Counter(
    "llm_gateway_tokens_total",
    "Total tokens consumed by tenant and model",
    ["tenant_id", "model", "type"],
)

# 3. Request duration histogram (custom buckets tuned for LLM latency: 50ms up to 60s)
LLM_REQUEST_DURATION_SECONDS = Histogram(
    "llm_gateway_request_duration_seconds",
    "Latency of LLM requests end-to-end",
    ["tenant_id", "model"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

# 4. Rate limit rejections
LLM_RATE_LIMIT_EXCEEDED_TOTAL = Counter(
    "llm_gateway_rate_limit_exceeded_total",
    "Count of requests rejected due to rate limiting",
    ["tenant_id"],
)