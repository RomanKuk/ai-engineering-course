from __future__ import annotations

from app.main import chat


def test_crew_architecture_returns_contract_compatible_response() -> None:
    response = chat({"message": "hello", "architecture": "crew"})

    assert response["architecture"] == "crew"
    assert response["route"] == "crew"
    assert response["intent"] == "crew_placeholder"
    assert response["guardrail_applied"] is False
    assert "trace" in response
    assert response["trace"]["route"] == "crew"
    assert response["trace"]["tools_used"] == []
