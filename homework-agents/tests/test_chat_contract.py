from __future__ import annotations

from app.main import chat


def test_chat_response_contains_trace_contract() -> None:
    response = chat({"message": "How much did I spend on coffee last week?"})
    assert "trace" in response
    trace = response["trace"]

    assert trace["intent"] == response["intent"]
    assert trace["intent_reason"] == response["intent_reason"]
    assert trace["route"] == response["route"]
    assert trace["guardrail_applied"] == response["guardrail_applied"]
    assert trace["tools_used"] == response["tools_used"]
    assert trace["tool_outputs"] == response["tool_outputs"]
