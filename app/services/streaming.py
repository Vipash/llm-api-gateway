import json
import logging
import time
from typing import AsyncGenerator

import httpx

from app.core.metrics import (
    LLM_REQUESTS_TOTAL,
    LLM_REQUEST_DURATION_SECONDS,
    LLM_TOKENS_TOTAL,
)
from app.services.analytics import log_request_and_usage

logger = logging.getLogger(__name__)


async def stream_chat_generator(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    body: dict,
    tenant_id: str,
    model_name: str,
    start_time: float,
) -> AsyncGenerator[bytes, None]:
    """Streams SSE chunks from upstream LLM to client, recording TTFT and usage metadata."""
    prompt_tokens = 0
    completion_tokens = 0
    first_token_recorded = False
    status_code = "200"

    try:
        async with client.stream(
            "POST",
            url,
            json=body,
            headers=headers,
            timeout=120.0,
        ) as upstream_response:
            status_code = str(upstream_response.status_code)

            # Handle immediate upstream errors
            if upstream_response.is_error:
                error_body = await upstream_response.aread()
                yield error_body
                return

            # Read raw line-by-line SSE chunks
            async for raw_line in upstream_response.aiter_lines():
                if not raw_line:
                    yield b"\n\n"
                    continue

                # Parse SSE data frame for metrics & TTFT
                if raw_line.startswith("data: "):
                    # Measure TTFT only when actual content payload arrives (excluding [DONE])
                    if not first_token_recorded and raw_line != "data: [DONE]":
                        ttft_ms = (time.perf_counter() - start_time) * 1000.0
                        logger.info(
                            "[STREAM] TTFT (Time To First Token): %.2fms",
                            ttft_ms,
                        )
                        first_token_recorded = True

                    if raw_line != "data: [DONE]":
                        try:
                            payload = json.loads(raw_line[6:])
                            usage = payload.get("usage")

                            if usage:
                                prompt_tokens = usage.get("prompt_tokens") or prompt_tokens
                                completion_tokens = usage.get("completion_tokens") or completion_tokens

                        except (json.JSONDecodeError, TypeError, AttributeError):
                            pass

                # Yield SSE chunk to client
                yield f"{raw_line}\n\n".encode("utf-8")

    except Exception as exc:
        logger.error("[STREAM ERROR] Connection broken: %s", exc)
        status_code = "502"
        raise

    finally:
        # Guarantee HTTP Client Close
        await client.aclose()

        total_latency_seconds = time.perf_counter() - start_time
        total_latency_ms = total_latency_seconds * 1000.0

        logger.info(
            "[STREAM] Finished in %.2fms. Recording metrics and analytics...",
            total_latency_ms,
        )

        # ---------------------------------------------------------
        # Prometheus metrics (Sync operations - always safe)
        # ---------------------------------------------------------
        LLM_REQUESTS_TOTAL.labels(
            tenant_id=tenant_id,
            model=model_name,
            status_code=status_code,
        ).inc()

        LLM_REQUEST_DURATION_SECONDS.labels(
            tenant_id=tenant_id,
            model=model_name,
        ).observe(total_latency_seconds)

        if prompt_tokens > 0:
            LLM_TOKENS_TOTAL.labels(
                tenant_id=tenant_id,
                model=model_name,
                type="prompt",
            ).inc(prompt_tokens)

        if completion_tokens > 0:
            LLM_TOKENS_TOTAL.labels(
                tenant_id=tenant_id,
                model=model_name,
                type="completion",
            ).inc(completion_tokens)

        # ---------------------------------------------------------
        # Postgres analytics logging
        # ---------------------------------------------------------
        dummy_usage_payload = json.dumps(
            {
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            }
        ).encode("utf-8")

        try:
            # Shield DB write task against event loop cancellation on disconnect
            import asyncio
            asyncio.create_task(
                log_request_and_usage(
                    tenant_id=tenant_id,
                    endpoint="/v1/chat/completions",
                    model=model_name,
                    latency_ms=total_latency_ms,
                    status_code=int(status_code),
                    raw_response_bytes=dummy_usage_payload,
                )
            )
        except Exception:
            logger.exception("[STREAM] Failed to schedule analytics task")