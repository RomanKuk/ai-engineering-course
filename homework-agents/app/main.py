from __future__ import annotations

from fastapi import FastAPI


app = FastAPI(title="Personal Finance Coach")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(body: dict) -> dict:
    architecture = body.get("architecture", "baseline")
    message = body.get("message", "")
    return {
        "architecture": architecture,
        "answer": "Placeholder response. Backend wiring starts in step 2.",
        "echo": message,
    }
