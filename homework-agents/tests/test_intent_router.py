from __future__ import annotations

from app.services.intent_router import classify_intent


def test_fraud_escalation_intent() -> None:
    result = classify_intent("I didn't make this Booking.com charge", has_context=True)
    assert result.intent == "fraud_escalation"


def test_out_of_scope_intent() -> None:
    result = classify_intent("Купи мені акції Apple", has_context=True)
    assert result.intent == "out_of_scope"


def test_clarification_needed_for_followup_without_context() -> None:
    result = classify_intent("А місяць?", has_context=False)
    assert result.intent == "clarification_needed"


def test_top_categories_intent() -> None:
    result = classify_intent("Top-5 categories for June", has_context=True)
    assert result.intent == "top_categories"


def test_spend_by_category_intent() -> None:
    result = classify_intent("Скільки витратила на каву?", has_context=True)
    assert result.intent == "spend_by_category"
