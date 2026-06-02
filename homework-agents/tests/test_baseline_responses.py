from __future__ import annotations

from app.main import chat


def test_spend_by_category_response_is_grounded() -> None:
    response = chat({"message": "How much did I spend on coffee last week?"})
    assert response["route"] == "baseline"
    assert response["intent"] == "spend_by_category"
    assert "spend_by_category" in response["tools_used"]
    assert "spend_by_category" in response["tool_outputs"]
    assert "$" in response["answer"]
    assert "Placeholder response" not in response["answer"]


def test_top_categories_response_uses_tool() -> None:
    response = chat({"message": "Top 5 categories this month"})
    assert response["intent"] == "top_categories"
    assert "top_categories" in response["tools_used"]
    assert isinstance(response["tool_outputs"].get("top_categories", {}).get("items", []), list)


def test_month_projection_response_uses_tool() -> None:
    response = chat({"message": "Will this month close in plus?"})
    assert response["intent"] == "month_projection"
    assert "project_month_end_balance" in response["tools_used"]
    assert "projected_balance" in response["tool_outputs"]["project_month_end_balance"]
