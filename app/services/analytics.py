from datetime import datetime, timezone
import json
import traceback
from sqlalchemy.dialects.postgresql import insert
from app.db import SessionLocal
from app.models import DailyUsage, RequestLog


async def log_request_and_usage(
    tenant_id: str,
    endpoint: str,
    model: str,
    latency_ms: float,
    status_code: int,
    raw_response_bytes: bytes,
) -> None:
    print(f"\n================ [ANALYTICS START] ================", flush=True)
    print(f"Tenant ID: {tenant_id} | Status: {status_code}", flush=True)

    try:
        prompt_tokens = 0
        completion_tokens = 0

        if raw_response_bytes and status_code == 200:
            try:
                data = json.loads(raw_response_bytes)
                usage = data.get("usage", {})
                prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
                completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            except Exception as parse_err:
                print(f"[ANALYTICS] JSON Parse Notice: {parse_err}", flush=True)

        today = datetime.now(timezone.utc).date()

        # Handle UUID or String tenant_id safely
        parsed_tenant_id = str(tenant_id)

        async with SessionLocal() as db:
            # 1. Insert RequestLog
            log_entry = RequestLog(
                tenant_id=parsed_tenant_id,
                endpoint=endpoint,
                model=model,
                status_code=status_code,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
            )
            db.add(log_entry)

            # 2. Upsert DailyUsage (using request_count & usage_date)
            stmt = insert(DailyUsage).values(
                tenant_id=parsed_tenant_id,
                usage_date=today,
                request_count=1,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "usage_date"],
                set_={
                    "request_count": DailyUsage.request_count + 1,
                    "prompt_tokens": DailyUsage.prompt_tokens + prompt_tokens,
                    "completion_tokens": DailyUsage.completion_tokens + completion_tokens,
                },
            )
            await db.execute(stmt)
            await db.commit()
            print(">>> [ANALYTICS SUCCESS] Row successfully written to Postgres!", flush=True)

    except Exception as err:
        print(">>> [ANALYTICS CRITICAL ERROR] Background task failed:", flush=True)
        traceback.print_exc()

    print("================ [ANALYTICS END] ================\n", flush=True)