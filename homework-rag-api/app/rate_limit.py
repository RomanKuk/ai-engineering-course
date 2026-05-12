from __future__ import annotations

import math
import os
import time

import redis

_client: redis.Redis | None = None
UPDATE_RETRIES = 5


def _get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            os.getenv("UPSTASH_REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
            socket_connect_timeout=2,
        )
    return _client


def _resolve_limit(api_key: str, limit: int | None) -> int:
    if limit is not None:
        return limit

    from app.auth import API_KEYS

    key_info = API_KEYS.get(api_key)
    if not key_info:
        raise ValueError(f"Unknown API key: {api_key}")
    return int(key_info["rate_limit_tokens_per_min"])


def _bucket_keys(api_key: str) -> tuple[str, str]:
    prefix = f"rl:{api_key}"
    return f"{prefix}:debt", f"{prefix}:updated_at"


def _refill_rate(limit: int) -> float:
    return limit / 60.0


def _decayed_debt(debt_raw: str | None, updated_at_raw: str | None, refill_rate: float, now: float) -> float:
    if debt_raw is None or updated_at_raw is None:
        return 0.0

    try:
        debt = float(debt_raw)
        updated_at = float(updated_at_raw)
    except (TypeError, ValueError):
        return 0.0

    elapsed = max(0.0, now - updated_at)
    return max(0.0, debt - (elapsed * refill_rate))


def _retry_after_seconds(current_debt: float, limit: int) -> int:
    refill_rate = _refill_rate(limit)
    debt_to_clear = max(0.0, current_debt - limit)
    return max(1, math.ceil(debt_to_clear / refill_rate))


def _state_ttl_seconds(current_debt: float, limit: int) -> int:
    refill_rate = _refill_rate(limit)
    return max(1, math.ceil(current_debt / refill_rate))


def check_capacity(api_key: str, limit: int) -> tuple[bool, int]:
    try:
        r = _get_redis()
        now = time.time()
        debt_key, updated_at_key = _bucket_keys(api_key)
        debt_raw, updated_at_raw = r.mget(debt_key, updated_at_key)
        current_debt = _decayed_debt(debt_raw, updated_at_raw, _refill_rate(limit), now)
        if current_debt >= limit:
            return False, _retry_after_seconds(current_debt, limit)
        return True, 0
    except redis.exceptions.RedisError as exc:
        print(f"[warn] Redis unavailable, skipping rate limit check: {exc}")
        return True, 0


def deduct_tokens(api_key: str, tokens: int, limit: int | None = None) -> None:
    if tokens <= 0:
        return

    try:
        resolved_limit = _resolve_limit(api_key, limit)
        r = _get_redis()
        debt_key, updated_at_key = _bucket_keys(api_key)
        refill_rate = _refill_rate(resolved_limit)

        for _ in range(UPDATE_RETRIES):
            now = time.time()
            with r.pipeline() as pipe:
                try:
                    pipe.watch(debt_key, updated_at_key)
                    debt_raw, updated_at_raw = pipe.mget(debt_key, updated_at_key)
                    current_debt = _decayed_debt(debt_raw, updated_at_raw, refill_rate, now)
                    new_debt = current_debt + tokens
                    ttl_seconds = _state_ttl_seconds(new_debt, resolved_limit)

                    pipe.multi()
                    pipe.set(debt_key, current_debt)
                    pipe.set(updated_at_key, now)
                    pipe.incrbyfloat(debt_key, tokens)
                    pipe.expire(debt_key, ttl_seconds)
                    pipe.expire(updated_at_key, ttl_seconds)
                    pipe.execute()
                    return
                except redis.exceptions.WatchError:
                    continue

        print(f"[warn] Redis contention, skipping token deduction for {api_key}")
    except redis.exceptions.RedisError as exc:
        print(f"[warn] Redis unavailable, skipping token deduction: {exc}")
