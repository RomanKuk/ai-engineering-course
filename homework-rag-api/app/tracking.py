import os
import sqlite3
import uuid
from datetime import date, datetime

from app.pricing import calculate_cost

DB_PATH = os.getenv("DB_PATH", "costs.db")

_langfuse = None


def _get_langfuse():
    global _langfuse
    if _langfuse is None and os.getenv("LANGFUSE_PUBLIC_KEY"):
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    return _langfuse


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            request_id  TEXT PRIMARY KEY,
            api_key     TEXT,
            model       TEXT,
            input_tokens  INTEGER,
            output_tokens INTEGER,
            cost_usd    REAL,
            latency_ms  INTEGER,
            ttft_ms     INTEGER,
            cache_hit   INTEGER,
            fallback_used INTEGER,
            output_filtered INTEGER DEFAULT 0,
            created_at  TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_request(
    *,
    api_key: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    ttft_ms: int,
    cache_hit: bool,
    fallback_used: bool,
    output_filtered: bool = False,
) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            api_key,
            model,
            input_tokens,
            output_tokens,
            cost_usd,
            latency_ms,
            ttft_ms,
            int(cache_hit),
            int(fallback_used),
            int(output_filtered),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    lf = _get_langfuse()
    if lf:
        try:
            lf.trace(
                name="rag-chat",
                metadata={
                    "api_key": api_key,
                    "model": model,
                    "cache_hit": cache_hit,
                    "fallback_used": fallback_used,
                    "cost_usd": cost_usd,
                    "latency_ms": latency_ms,
                },
            )
        except Exception as exc:
            print(f"[warn] Langfuse trace failed: {exc}")


def get_today_usage(api_key: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(input_tokens+output_tokens),0), COALESCE(SUM(cost_usd),0) "
        "FROM requests WHERE api_key=? AND created_at LIKE ?",
        (api_key, f"{today}%"),
    ).fetchone()
    conn.close()
    return {"requests": row[0], "tokens": row[1], "cost_usd": round(row[2], 6)}


def get_breakdown(api_key: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT model, COUNT(*), SUM(input_tokens+output_tokens), SUM(cost_usd), "
        "AVG(latency_ms), SUM(cache_hit), SUM(fallback_used) "
        "FROM requests WHERE api_key=? GROUP BY model",
        (api_key,),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*), SUM(cache_hit), SUM(fallback_used) FROM requests WHERE api_key=?",
        (api_key,),
    ).fetchone()
    p95_row = conn.execute(
        "SELECT latency_ms FROM requests WHERE api_key=? ORDER BY latency_ms",
        (api_key,),
    ).fetchall()
    conn.close()

    n = total[0] or 1
    cache_hit_rate = round((total[1] or 0) / n, 4)
    fallback_rate = round((total[2] or 0) / n, 4)
    p95 = p95_row[int(len(p95_row) * 0.95)][0] if p95_row else 0

    return {
        "by_model": [
            {
                "model": r[0],
                "requests": r[1],
                "tokens": r[2],
                "cost_usd": round(r[3], 6),
                "avg_latency_ms": round(r[4]),
                "cache_hits": r[5],
                "fallbacks": r[6],
            }
            for r in rows
        ],
        "cache_hit_rate": cache_hit_rate,
        "fallback_rate": fallback_rate,
        "p95_latency_ms": p95,
    }
