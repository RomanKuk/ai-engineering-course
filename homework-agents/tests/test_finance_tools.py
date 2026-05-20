from __future__ import annotations

from pathlib import Path

from app.tools.finance_tools import (
    list_tools,
    tool_compare_category_between_periods,
    tool_last_payment_by_merchant,
    tool_project_month_end_balance,
    tool_recent_credit_card_transactions,
    tool_spend_by_category,
    tool_top_categories,
)


def _csv_path() -> Path:
    return Path(__file__).resolve().parents[1] / "starter" / "data" / "transactions.csv"


def test_tool_registry_contains_expected_names() -> None:
    names = {item["name"] for item in list_tools()}
    assert "spend_by_category" in names
    assert "top_categories" in names
    assert "project_month_end_balance" in names


def test_spend_by_category_tool_shape() -> None:
    result = tool_spend_by_category(_csv_path(), category="coffee", period="last_week")
    assert result["tool"] == "spend_by_category"
    assert result["category"] == "coffee"
    assert isinstance(result["total"], float)


def test_top_categories_tool_shape() -> None:
    result = tool_top_categories(_csv_path(), period="current_month", limit=5)
    assert result["tool"] == "top_categories"
    assert isinstance(result["items"], list)
    assert len(result["items"]) <= 5


def test_last_payment_tool_shape() -> None:
    result = tool_last_payment_by_merchant(_csv_path(), merchant="Netflix")
    assert result["tool"] == "last_payment_by_merchant"
    assert isinstance(result["found"], bool)


def test_recent_credit_card_transactions_tool_shape() -> None:
    result = tool_recent_credit_card_transactions(_csv_path(), limit=3)
    assert result["tool"] == "recent_credit_card_transactions"
    assert len(result["items"]) <= 3


def test_compare_periods_tool_shape() -> None:
    result = tool_compare_category_between_periods(
        _csv_path(), category="delivery", left_period="current_month", right_period="last_week"
    )
    assert result["tool"] == "compare_category_between_periods"
    assert "delta" in result


def test_project_month_end_balance_tool_shape() -> None:
    result = tool_project_month_end_balance(_csv_path())
    assert result["tool"] == "project_month_end_balance"
    assert "projected_balance" in result
