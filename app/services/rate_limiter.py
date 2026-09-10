import time
import uuid
from redis.asyncio import Redis

_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

-- Prune requests older than the sliding window
local clear_before = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)

-- Check current count
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    -- Record this request
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window))
    
    -- Get oldest element timestamp to compute reset
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local reset_seconds = math.ceil(window)
    if #oldest > 0 then
        local oldest_ts = tonumber(oldest[2])
        reset_seconds = math.max(1, math.ceil((oldest_ts + window) - now))
    end
    
    return {1, limit - current_count - 1, reset_seconds}
else
    redis.call('EXPIRE', key, math.ceil(window))
    
    -- Get oldest element timestamp to know when the next slot opens
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local reset_seconds = math.ceil(window)
    if #oldest > 0 then
        local oldest_ts = tonumber(oldest[2])
        reset_seconds = math.max(1, math.ceil((oldest_ts + window) - now))
    end
    
    return {0, 0, reset_seconds}
end
"""

async def is_rate_limited(
    redis: Redis,
    tenant_id: str,
    limit: int,
    window_seconds: int = 60,
) -> tuple[bool, int, int]:
    """
    Returns (is_allowed, remaining, reset_seconds).
    Uses seconds with sub-millisecond precision for timestamps.
    """
    now = time.time()
    member = f"{now}:{uuid.uuid4().hex[:8]}"

    result = await redis.eval(
        _SLIDING_WINDOW_LUA,
        1,
        f"rate_limit:{tenant_id}",
        now,
        float(window_seconds),
        limit,
        member,
    )
    allowed, remaining, reset_seconds = result
    return bool(int(allowed)), max(0, int(remaining)), int(reset_seconds)