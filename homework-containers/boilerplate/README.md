# Lesson 13 — Containerized RAG App

## How to run

```bash
cp .env.example .env   # add your OPENAI_API_KEY
docker compose up --build
```

Test the endpoint:

```bash
curl -X POST localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the return policy?"}'
```

## Image metrics

| Metric | Naive | Multi-stage |
|---|---|---|
| Image size | 1.22 GB | 232 MB |
| Build time | 134 s | 9 s |
| Rebuild after code change | 74 s | 5 s |
| Cold start (to `/health=ok`) | 6.6 s | 8.1 s |

## Screenshots

<!-- docker images (both images) -->
<!-- curl /ask response -->
<!-- docker compose ps -->
