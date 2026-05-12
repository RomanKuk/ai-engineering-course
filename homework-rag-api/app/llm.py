from __future__ import annotations

import asyncio
import os
import time

from openai import AsyncOpenAI, APIStatusError

TIMEOUT_SEC = 15.0
CB_THRESHOLD = 5
CB_WINDOW = 60.0

_client: AsyncOpenAI | None = None
_cb: dict[str, dict] = {}

NON_RETRYABLE = {400, 401, 403, 422}


def get_provider() -> str:
    """OpenAI is default; fall back to OpenRouter if no OpenAI key."""
    return "openai" if os.getenv("OPENAI_API_KEY") else "openrouter"


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if get_provider() == "openai":
            _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        else:
            _client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv("OPENROUTER_API_KEY"),
            )
    return _client


def _cb_open(model: str) -> bool:
    state = _cb.get(model)
    if not state:
        return False
    if time.time() < state.get("blocked_until", 0):
        return True
    now = time.time()
    state["times"] = [t for t in state.get("times", []) if now - t < CB_WINDOW]
    if len(state["times"]) >= CB_THRESHOLD:
        state["blocked_until"] = now + CB_WINDOW
        return True
    return False


def _cb_record(model: str) -> None:
    if model not in _cb:
        _cb[model] = {"times": [], "blocked_until": 0.0}
    _cb[model]["times"].append(time.time())


class StreamResult:
    def __init__(self):
        self.model = ""
        self.fallback_used = False
        self.input_tokens = 0
        self.output_tokens = 0


async def stream_with_fallback(models: list[str], messages: list[dict], result: StreamResult):
    client = _get_client()
    last_err = "no models tried"

    for i, model in enumerate(models):
        if _cb_open(model):
            last_err = f"{model} circuit open"
            continue

        try:
            stream = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=True,
                    stream_options={"include_usage": True},
                ),
                timeout=TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            _cb_record(model)
            last_err = f"{model} timeout"
            continue
        except APIStatusError as exc:
            if exc.status_code in NON_RETRYABLE:
                raise
            _cb_record(model)
            last_err = f"{model} {exc.status_code}"
            continue

        result.model = model
        result.fallback_used = i > 0

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
            if chunk.usage:
                result.input_tokens = chunk.usage.prompt_tokens or 0
                result.output_tokens = chunk.usage.completion_tokens or 0
        return

    raise RuntimeError(f"All models failed: {last_err}")
