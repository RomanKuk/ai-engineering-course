from __future__ import annotations

from app.main import chat


def test_fraud_guardrail_short_circuits_chat() -> None:
    response = chat({"message": "I did not make this Booking.com charge, how much coffee did I spend?"})
    assert response["intent"] == "fraud_escalation"
    assert response["route"] == "guardrail"
    assert response["guardrail_applied"] is True
    assert "disputed transaction" in response["answer"].lower()


def test_out_of_scope_guardrail_short_circuits_chat() -> None:
    response = chat({"message": "buy stocks for me"})
    assert response["intent"] == "out_of_scope"
    assert response["route"] == "guardrail"
    assert response["guardrail_applied"] is True
    assert "cannot help with investing" in response["answer"].lower()


def test_clarification_guardrail_when_followup_has_no_context() -> None:
    response = chat({"message": "and for the month?", "session_id": "no-context-session"})
    assert response["intent"] == "clarification_needed"
    assert response["route"] == "guardrail"
    assert response["guardrail_applied"] is True


def test_non_guardrail_intent_uses_baseline_route() -> None:
    response = chat({"message": "How much did I spend on coffee last week?"})
    assert response["intent"] == "spend_by_category"
    assert response["route"] == "baseline"
    assert response["guardrail_applied"] is False
