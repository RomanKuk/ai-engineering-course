from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from dotenv import load_dotenv
load_dotenv()
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth import get_api_key
from app.cache import cache_check, cache_store, init_cache_collection
from app.llm import StreamResult, get_provider, stream_with_fallback
from app.pricing import calculate_cost
from app.rag import embed, retrieve
from app.rate_limit import check_capacity, deduct_tokens
from app.security import check_input, check_output
from app.tracking import get_breakdown, get_today_usage, init_db, log_request

semaphore = asyncio.Semaphore(20)
active_streams: int = 0
aborted_streams: int = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        await init_cache_collection()
    except Exception as exc:
        print(f"[warn] Qdrant unavailable at startup ({exc}). Cache disabled until connection is restored.")
    yield


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _check_env() -> dict:
    llm_ok = bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY"))
    vars_status = {
        "llm_provider": "openai" if os.getenv("OPENAI_API_KEY") else ("openrouter" if os.getenv("OPENROUTER_API_KEY") else None),
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "OPENROUTER_API_KEY": bool(os.getenv("OPENROUTER_API_KEY")),
        "QDRANT_URL": bool(os.getenv("QDRANT_URL")),
        "QDRANT_API_KEY": bool(os.getenv("QDRANT_API_KEY")),
        "UPSTASH_REDIS_URL": bool(os.getenv("UPSTASH_REDIS_URL")),
        "LANGFUSE_PUBLIC_KEY": bool(os.getenv("LANGFUSE_PUBLIC_KEY")),
        "LANGFUSE_SECRET_KEY": bool(os.getenv("LANGFUSE_SECRET_KEY")),
    }
    missing = [k for k, v in vars_status.items() if not v and k not in ("llm_provider", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")]
    if not llm_ok:
        missing.append("OPENAI_API_KEY or OPENROUTER_API_KEY")
    return {"env": vars_status, "missing": missing, "ready": len(missing) == 0}


@app.get("/health")
async def health():
    return {"status": "ok", "active_streams": active_streams, "aborted_streams": aborted_streams}


@app.get("/admin/status")
async def admin_status(key_info: dict = Depends(get_api_key)):
    if key_info["tier"] != "demo-enterprise":
        raise HTTPException(status_code=403, detail="Enterprise tier required")
    env = _check_env()
    return {"active_streams": active_streams, "aborted_streams": aborted_streams, **env}


@app.get("/usage/today")
async def usage_today(key_info: dict = Depends(get_api_key)):
    return get_today_usage(key_info["key"])


@app.get("/usage/breakdown")
async def usage_breakdown(key_info: dict = Depends(get_api_key)):
    return get_breakdown(key_info["key"])


@app.post("/index/rebuild")
async def index_rebuild(key_info: dict = Depends(get_api_key)):
    if key_info["tier"] != "demo-enterprise":
        raise HTTPException(status_code=403, detail="Enterprise tier required")
    import subprocess, sys
    result = subprocess.run([sys.executable, "scripts/index.py"], capture_output=True, text=True)
    return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}


@app.post("/chat/stream")
async def chat_stream(body: ChatRequest, request: Request, key_info: dict = Depends(get_api_key)):
    global active_streams, aborted_streams

    api_key = key_info["key"]
    provider = get_provider()
    models: list[str] = key_info[f"{provider}_models"]
    rate_limit: int = key_info["rate_limit_tokens_per_min"]

    check_input(body.message)

    ok, retry_after = check_capacity(api_key, rate_limit)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    query_vec = embed(body.message)

    cached = await cache_check(query_vec)
    if cached:
        async def _stream_cached():
            for word in cached.split():
                yield _sse({"type": "token", "content": word + " "})
                await asyncio.sleep(0.005)
            log_request(
                api_key=api_key, model="cache", input_tokens=0, output_tokens=0,
                cost_usd=0.0, latency_ms=0, ttft_ms=0, cache_hit=True, fallback_used=False,
            )
            yield _sse({"type": "done", "usage": {"input_tokens": 0, "output_tokens": 0}, "cost_usd": 0.0, "cache_hit": True, "sources": []})

        return StreamingResponse(_stream_cached(), media_type="text/event-stream")

    chunks = await retrieve(query_vec)
    sources = [c["id"] for c in chunks]
    context = "\n\n".join(c["text"] for c in chunks)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. Answer the user question based solely on the provided context. "
                "Always respond in the same language the user asked in. "
                "If the context is in Ukrainian, you may use Ukrainian terminology.\n\n"
                f"<context>\n{context}\n</context>"
            ),
        },
        {"role": "user", "content": f"<user_query>{body.message}</user_query>"},
    ]

    result = StreamResult()
    start_time = time.time()
    ttft_ms: int | None = None

    async def generate():
        global active_streams, aborted_streams
        nonlocal ttft_ms

        full_response: list[str] = []
        disconnected = False

        async with semaphore:
            active_streams += 1
            try:
                async for token in stream_with_fallback(models, messages, result):
                    if await request.is_disconnected():
                        disconnected = True
                        aborted_streams += 1
                        return
                    if ttft_ms is None:
                        ttft_ms = int((time.time() - start_time) * 1000)
                    full_response.append(token)
                    yield _sse({"type": "token", "content": token})

                if not disconnected:
                    response_text = "".join(full_response)
                    output_filtered = check_output(response_text)
                    latency_ms = int((time.time() - start_time) * 1000)
                    cost = calculate_cost(result.model, result.input_tokens, result.output_tokens)

                    deduct_tokens(api_key, result.input_tokens + result.output_tokens, rate_limit)

                    log_request(
                        api_key=api_key,
                        model=result.model,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cost_usd=cost,
                        latency_ms=latency_ms,
                        ttft_ms=ttft_ms or 0,
                        cache_hit=False,
                        fallback_used=result.fallback_used,
                        output_filtered=output_filtered,
                    )

                    await cache_store(query_vec, body.message, response_text, result.model)

                    yield _sse({"type": "done", "usage": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens}, "cost_usd": cost, "cache_hit": False, "sources": sources})

            except asyncio.CancelledError:
                aborted_streams += 1
            except RuntimeError as exc:
                yield _sse({"type": "error", "detail": str(exc)})
            finally:
                active_streams -= 1

    return StreamingResponse(generate(), media_type="text/event-stream")
