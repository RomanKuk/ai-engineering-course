from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.services.analytics import load_analytics, summary


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


@app.get("/debug/summary")
def debug_summary() -> dict:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "starter" / "data" / "transactions.csv"
    analytics = load_analytics(csv_path)
    return summary(analytics)
