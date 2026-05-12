from fastapi import Header, HTTPException

# Each tier has separate model chains for OpenAI and OpenRouter.
# OpenAI is the default provider (set OPENAI_API_KEY).
# OpenRouter is used when only OPENROUTER_API_KEY is set.
API_KEYS: dict[str, dict] = {
    "demo-free-key": {
        "tier": "demo-free",
        "rate_limit_tokens_per_min": 5_000,
        "openai_models": [
            "gpt-4o-mini",
            "gpt-3.5-turbo",
            "gpt-4o-mini",          # last-resort same as primary
        ],
        "openrouter_models": [
            "meta-llama/llama-3.1-8b-instruct:free",
            "google/gemini-flash-1.5:free",
            "meta-llama/llama-3.2-3b-instruct:free",
        ],
    },
    "demo-pro-key": {
        "tier": "demo-pro",
        "rate_limit_tokens_per_min": 20_000,
        "openai_models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo",
        ],
        "openrouter_models": [
            "mistralai/mistral-small-3.1-24b-instruct:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "google/gemini-flash-1.5:free",
        ],
    },
    "demo-enterprise-key": {
        "tier": "demo-enterprise",
        "rate_limit_tokens_per_min": 100_000,
        "openai_models": [
            "gpt-4o",
            "o1-mini",
            "gpt-4o-mini",
        ],
        "openrouter_models": [
            "openai/gpt-4o-mini",
            "mistralai/mistral-small-3.1-24b-instruct:free",
            "meta-llama/llama-3.1-8b-instruct:free",
        ],
    },
}


async def get_api_key(x_api_key: str = Header(...)) -> dict:
    info = API_KEYS.get(x_api_key)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {"key": x_api_key, **info}
