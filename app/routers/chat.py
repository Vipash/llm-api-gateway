import asyncio
import json
import time
import traceback
from typing import Annotated

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.metrics import (
    LLM_REQUEST_DURATION_SECONDS,
    LLM_REQUESTS_TOTAL,
    LLM_TOKENS_TOTAL,
)
from app.deps import get_current_tenant, rate_limit_check
from app.models import Tenant
from app.services.analytics import log_request_and_usage
from app.services.streaming import stream_chat_generator

router = APIRouter(prefix="/v1", tags=["chat"])

# Reuse default timeout configuration
timeout = httpx.Timeout(
    connect=10.0,
    read=120.0,
    write=10.0,
    pool=10.0,
)


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    _: Annotated[None, Depends(rate_limit_check)],
) -> Response:
    start_time = time.perf_counter()
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raw_content = b""
    headers = {"Content-Type": "application/json"}
    is_streaming = False

    try:
        # ---------------------------------------------------------
        # 1. PARSE REQUEST
        # ---------------------------------------------------------
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            status_code = status.HTTP_400_BAD_REQUEST
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload provided in request body.",
            )

        model_name = body.get("model", settings.llm_model_name)
        body["model"] = model_name
        is_streaming = body.get("stream", False)
        extra_headers = getattr(request.state, "rate_limit_headers", {})

        # ---------------------------------------------------------
        # 2. UPSTREAM MOCK MODE (FOR LOAD TESTING)
        # ---------------------------------------------------------
        if settings.mock_upstream:
            # Simulate a realistic 50ms network/inference round-trip
            await asyncio.sleep(0.050)
            mock_payload = {
                "id": "chatcmpl-mock-123",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Mock response",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 10,
                    "total_tokens": 25,
                },
            }
            raw_content = json.dumps(mock_payload).encode("utf-8")
            status_code = status.HTTP_200_OK
            return Response(
                content=raw_content,
                status_code=status_code,
                media_type="application/json",
                headers={
                    **extra_headers,
                    "x-mock-mode": "true",
                },
            )

        # ---------------------------------------------------------
        # 3. REAL UPSTREAM HTTP CALL (OLLAMA / OPENAI)
        # ---------------------------------------------------------
        if is_streaming and "stream_options" not in body:
            body["stream_options"] = {"include_usage": True}

        url = (
            f"{settings.llm_provider_base_url.rstrip('/')}"
            "/chat/completions"
        )

        # PATH 1: STREAMING (SSE)
        if is_streaming:
            streaming_client = httpx.AsyncClient(timeout=timeout)
            return StreamingResponse(
                stream_chat_generator(
                    client=streaming_client,
                    url=url,
                    headers=headers,
                    body=body,
                    tenant_id=str(tenant.id),
                    model_name=model_name,
                    start_time=start_time,
                ),
                media_type="text/event-stream",
                headers=extra_headers,
            )

        # PATH 2: BUFFERED JSON (stream=false)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                upstream = await client.post(
                    url,
                    json=body,
                    headers=headers,
                )
                status_code = upstream.status_code
                raw_content = upstream.content
                content_type = upstream.headers.get(
                    "content-type",
                    "application/json",
                )
            except httpx.ReadTimeout:
                status_code = status.HTTP_504_GATEWAY_TIMEOUT
                raw_content = (
                    b'{"detail": '
                    b'"Upstream LLM provider timed out processing the request."}'
                )
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Upstream LLM provider timed out processing the request.",
                )

        return Response(
            content=raw_content,
            status_code=status_code,
            media_type=content_type,
            headers=extra_headers,
        )

    except Exception as exc:
        if isinstance(exc, HTTPException):
            status_code = exc.status_code
        else:
            print("\n--- SYNCHRONOUS ROUTE ERROR ---", flush=True)
            traceback.print_exc()
            print("--------------------------------\n", flush=True)
        raise exc

    finally:
        # ---------------------------------------------------------
        # 4. PROMETHEUS METRICS + ANALYTICS
        # ---------------------------------------------------------
        if not is_streaming:
            duration_seconds = time.perf_counter() - start_time
            latency_ms = duration_seconds * 1000.0
            resolved_model = (
                body.get("model", settings.llm_model_name)
                if "body" in locals() and isinstance(body, dict)
                else settings.llm_model_name
            )

            LLM_REQUESTS_TOTAL.labels(
                tenant_id=str(tenant.id),
                model=resolved_model,
                status_code=str(status_code),
            ).inc()

            LLM_REQUEST_DURATION_SECONDS.labels(
                tenant_id=str(tenant.id),
                model=resolved_model,
            ).observe(duration_seconds)

            if status_code == status.HTTP_200_OK and raw_content:
                try:
                    data = json.loads(raw_content)
                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0) or 0
                    completion_tokens = usage.get("completion_tokens", 0) or 0

                    if prompt_tokens > 0:
                        LLM_TOKENS_TOTAL.labels(
                            tenant_id=str(tenant.id),
                            model=resolved_model,
                            type="prompt",
                        ).inc(prompt_tokens)

                    if completion_tokens > 0:
                        LLM_TOKENS_TOTAL.labels(
                            tenant_id=str(tenant.id),
                            model=resolved_model,
                            type="completion",
                        ).inc(completion_tokens)
                except Exception:
                    pass

            background_tasks.add_task(
                log_request_and_usage,
                tenant_id=str(tenant.id),
                endpoint="/v1/chat/completions",
                model=resolved_model,
                latency_ms=latency_ms,
                status_code=status_code,
                raw_response_bytes=raw_content,
            )