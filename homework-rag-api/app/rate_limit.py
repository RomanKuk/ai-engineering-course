from __future__ import annotations

import os
import redis

_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            os.getenv("UPSTASH_REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
            socket_connect_timeout=2,
        )
    return _client


def check_capacity(api_key: str, limit: int) -> tuple[bool, int]:
    try:
        r = _get_redis()
        key = f"rl:{api_key}"
        current = r.get(key)
        if current is not None and int(current) >= limit:
            ttl = r.ttl(key)
            return False, max(ttl, 1)
        return True, 0
    except redis.exceptions.RedisError as exc:
        print(f"[warn] Redis unavailable, skipping rate limit check: {exc}")
        return True, 0


def deduct_tokens(api_key: str, tokens: int) -> None:
    try:
        r = _get_redis()
        key = f"rl:{api_key}"
        new_val = r.incrby(key, tokens)
        if new_val == tokens:
            r.expire(key, 60)
    except redis.exceptions.RedisError as exc:
        print(f"[warn] Redis unavailable, skipping token deduction: {exc}")
