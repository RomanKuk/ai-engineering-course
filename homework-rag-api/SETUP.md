# Setup & Run Guide

## 1. Create virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Unix
pip install -r requirements.txt
```

## 2. Configure environment variables

```bash
cp .env.example .env
```

### LLM Provider — pick one (or both)

**OpenAI (default).** If `OPENAI_API_KEY` is set, it is used automatically.

| Variable | Where to get it |
|---|---|
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |

**OpenRouter (fallback).** Used only when `OPENAI_API_KEY` is empty.

| Variable | Where to get it |
|---|---|
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys (add $1–5 credit, or use `:free` models) |

If both keys are set, OpenAI wins.

### Other required variables

| Variable | Where to get it |
|---|---|
| `QDRANT_URL` | https://cloud.qdrant.io → create free cluster → copy URL |
| `QDRANT_API_KEY` | Same Qdrant Cloud cluster page |
| `UPSTASH_REDIS_URL` | https://upstash.com → create Redis DB → copy `rediss://` URL |
| `LANGFUSE_PUBLIC_KEY` | https://cloud.langfuse.com → Settings → API Keys |
| `LANGFUSE_SECRET_KEY` | Same page |

## 3. Add your document

The indexer defaults to `data/test.pdf`. To use a different file:

```bash
python scripts/index.py --source data/yourfile.pdf
# or markdown:
python scripts/index.py --source data/yourfile.md
```

## 4. Index the document

```bash
python scripts/index.py
```

Expected output:
```
Reading data/test.pdf ...
Chunks: 42
Batches: 100%|████| 2/2
Indexed 42 chunks into 'chunks_collection'
```

## 5. Run locally

```bash
uvicorn app.main:app --reload
```

## 6. Test locally

### 6.1 Health check — confirm the server is up

```bash
curl http://localhost:8000/health
```

Expected:
```json
{"status":"ok","active_streams":0,"aborted_streams":0}
```

---

### 6.2 First RAG query (cache MISS)

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-free-key" \
  -d "{\"message\": \"What is this document about?\"}"
```

`-N` disables curl buffering so tokens appear one by one.

Expected: a stream of `token` events followed by a `done` event:
```
data: {"type":"token","content":"This "}
data: {"type":"token","content":"document "}
...
data: {"type":"done","usage":{"input_tokens":312,"output_tokens":74},"cost_usd":0.000063,"cache_hit":false,"sources":["chunk_3","chunk_7","chunk_12"]}
```

---

### 6.3 Same query again (cache HIT)

Run the identical (or semantically similar) curl command a second time.  
Response arrives near-instantly — no LLM call is made.

Expected `done` event: `"cache_hit": true`, `"cost_usd": 0.0`.

---

### 6.4 Auth checks

Missing key → `422`:
```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"test\"}"
```

Wrong key → `401`:
```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: wrong-key" \
  -d "{\"message\": \"test\"}"
```

---

### 6.5 Rate limit

Send several requests quickly with `demo-free-key` (5 000 token/min limit).  
On Windows PowerShell:

```powershell
1..6 | ForEach-Object {
  Start-Job {
    Invoke-RestMethod -Method Post http://localhost:8000/chat/stream `
      -Headers @{"X-API-Key"="demo-free-key";"Content-Type"="application/json"} `
      -Body '{"message":"Summarize everything in full detail with examples"}'
  }
}
```

One or more requests will return `429 Too Many Requests` with a `Retry-After` header.

---

### 6.6 Usage stats

```bash
curl http://localhost:8000/usage/today -H "X-API-Key: demo-free-key"
curl http://localhost:8000/usage/breakdown -H "X-API-Key: demo-free-key"
```

---

### 6.7 Fallback test

In [app/auth.py](app/auth.py) change the first entry in `openai_models` for `demo-free-key` to `"gpt-9999-fake"`, restart uvicorn, send a query.  
The service auto-switches to `gpt-3.5-turbo`. Check `/usage/breakdown` — `fallback_rate` should be `1.0`.  
Revert the change when done.

---

### 6.8 Rebuild index (enterprise only)

```bash
curl -X POST http://localhost:8000/index/rebuild -H "X-API-Key: demo-enterprise-key"
```

## 7. Deploy to Fly.io

```bash
# Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login
fly launch --no-deploy          # creates app, updates fly.toml
fly secrets set \
  HF_TOKEN=hf_... \
  OPENAI_API_KEY=sk-... \
  QDRANT_URL=https://... \
  QDRANT_API_KEY=... \
  UPSTASH_REDIS_URL=rediss://... \
  LANGFUSE_PUBLIC_KEY=... \
  LANGFUSE_SECRET_KEY=...
fly deploy
fly open                        # opens public URL
```

`fly.toml` already has `auto_stop_machines = false` — required for SSE streaming to work correctly.

## 8. Verify Langfuse

Open https://cloud.langfuse.com → Traces.
Each `/chat/stream` call appears as a trace with `model`, `cache_hit`, `fallback_used`, `cost_usd`, and `latency_ms`.

---

## API keys for testing

| Key | Tier | Token limit/min | OpenAI models | OpenRouter models |
|---|---|---|---|---|
| `demo-free-key` | free | 5,000 | gpt-4o-mini → gpt-3.5-turbo | llama-3.1-8b → gemini-flash → llama-3.2-3b |
| `demo-pro-key` | pro | 20,000 | gpt-4o → gpt-4o-mini → gpt-3.5-turbo | mistral-small → llama-3.1-8b → gemini-flash |
| `demo-enterprise-key` | enterprise | 100,000 | gpt-4o → o1-mini → gpt-4o-mini | openai/gpt-4o-mini → mistral-small → llama-3.1-8b |
