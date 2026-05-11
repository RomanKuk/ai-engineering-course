PRICING: dict[str, dict[str, float]] = {
    # OpenAI models (native names)
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "o1-mini": {"input": 1.10, "output": 4.40},
    "o1": {"input": 15.0, "output": 60.0},
    # OpenRouter models (provider/name format)
    "openai/gpt-4o": {"input": 5.0, "output": 15.0},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "meta-llama/llama-3.1-8b-instruct:free": {"input": 0.0, "output": 0.0},
    "google/gemini-flash-1.5:free": {"input": 0.0, "output": 0.0},
    "meta-llama/llama-3.2-3b-instruct:free": {"input": 0.0, "output": 0.0},
    "mistralai/mistral-small-3.1-24b-instruct:free": {"input": 0.0, "output": 0.0},
    "anthropic/claude-3.5-sonnet": {"input": 3.0, "output": 15.0},
    "mistralai/mistral-large": {"input": 2.0, "output": 6.0},
}

_DEFAULT = {"input": 1.0, "output": 3.0}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICING.get(model, _DEFAULT)
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000
