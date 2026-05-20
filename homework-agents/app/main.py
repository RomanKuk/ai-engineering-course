from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.schemas import ChatRequest, ChatResponse
from app.services.analytics import load_analytics, summary
from app.services.baseline_runtime import BaselineRuntime
from app.services.crew_runtime import CrewRuntime
from app.tools import (
    list_tools,
    tool_compare_category_between_periods,
    tool_last_payment_by_merchant,
    tool_project_month_end_balance,
    tool_recent_credit_card_transactions,
    tool_spend_by_category,
    tool_top_categories,
)


app = FastAPI(title="Personal Finance Coach")
csv_path = Path(__file__).resolve().parents[1] / "starter" / "data" / "transactions.csv"
runtime = BaselineRuntime(csv_path)
crew_runtime = CrewRuntime(csv_path)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(body: dict) -> dict:
    request = ChatRequest.model_validate(body)
    payload = request.model_dump()
    if request.architecture == "crew":
        return crew_runtime.handle_chat(payload)
    return runtime.handle_chat(payload)


@app.get("/debug/summary")
def debug_summary() -> dict:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "starter" / "data" / "transactions.csv"
    analytics = load_analytics(csv_path)
    return summary(analytics)


@app.get("/debug/tools")
def debug_tools() -> dict:
    return {"tools": list_tools()}


@app.post("/debug/tool-call")
def debug_tool_call(body: dict) -> dict:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "starter" / "data" / "transactions.csv"

    tool = str(body.get("tool", "")).strip()
    args = body.get("args", {})
    if not isinstance(args, dict):
        return {"ok": False, "error": "args must be an object"}

    if tool == "spend_by_category":
        return {"ok": True, "result": tool_spend_by_category(csv_path, **args)}
    if tool == "top_categories":
        return {"ok": True, "result": tool_top_categories(csv_path, **args)}
    if tool == "last_payment_by_merchant":
        return {"ok": True, "result": tool_last_payment_by_merchant(csv_path, **args)}
    if tool == "recent_credit_card_transactions":
        return {"ok": True, "result": tool_recent_credit_card_transactions(csv_path, **args)}
    if tool == "compare_category_between_periods":
        return {"ok": True, "result": tool_compare_category_between_periods(csv_path, **args)}
    if tool == "project_month_end_balance":
        return {"ok": True, "result": tool_project_month_end_balance(csv_path)}

    return {"ok": False, "error": f"Unknown tool '{tool}'"}
