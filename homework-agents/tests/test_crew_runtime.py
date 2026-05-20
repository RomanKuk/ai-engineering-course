from __future__ import annotations

from app.main import chat


def test_crew_factual_query_uses_router_analyst_coach() -> None:
    response = chat({"message": "How much did I spend on coffee last week?", "architecture": "crew"})
    assert response["architecture"] == "crew"
    assert response["route"] == "crew"
    assert response["intent"] == "spend_by_category"
    assert "spend_by_category" in response["tools_used"]
    assert "crew_metrics" in response["tool_outputs"]


def test_crew_savings_query_uses_multiple_tools() -> None:
    response = chat({"message": "Where can I save $200 this month?", "architecture": "crew"})
    assert response["intent"] == "savings_advice"
    assert "top_categories" in response["tools_used"]
    assert "project_month_end_balance" in response["tools_used"]


def test_crew_multi_step_compare_query() -> None:
    response = chat({"message": "Compare delivery this month vs last week", "architecture": "crew"})
    assert response["intent"] == "compare_periods"
    assert "compare_category_between_periods" in response["tools_used"]
    assert "delta" in response["tool_outputs"]["analyst"]["facts"]["compare_category_between_periods"]


def test_crew_guardrail_fraud_short_circuits() -> None:
    response = chat({"message": "I did not make this Booking.com charge", "architecture": "crew"})
    assert response["route"] == "guardrail"
    assert response["guardrail_applied"] is True
    assert response["intent"] == "fraud_escalation"


def test_crew_follow_up_uses_context() -> None:
    session_id = "crew-follow-up"
    first = chat(
        {
            "message": "How much did I spend on coffee last week?",
            "architecture": "crew",
            "session_id": session_id,
        }
    )
    second = chat(
        {
            "message": "And for the month?",
            "architecture": "crew",
            "session_id": session_id,
        }
    )

    assert first["resolved_category"] == "coffee"
    assert second["resolved_category"] == "coffee"
    assert second["resolved_period"] == "current_month"
