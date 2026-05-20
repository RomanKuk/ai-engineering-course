from __future__ import annotations

from pathlib import Path

from app.services.baseline_runtime import BaselineRuntime


def test_runtime_handles_baseline_chat_and_returns_trace() -> None:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "starter" / "data" / "transactions.csv"
    runtime = BaselineRuntime(csv_path)

    response = runtime.handle_chat({"message": "How much did I spend on coffee last week?"})

    assert response["route"] == "baseline"
    assert response["intent"] == "spend_by_category"
    assert "trace" in response
    assert response["trace"]["tools_used"] == response["tools_used"]
