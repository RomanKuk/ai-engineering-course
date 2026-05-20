from __future__ import annotations

from app.main import chat
from app.services.session_context import SessionContextStore


def test_session_context_store_persists_updates() -> None:
    store = SessionContextStore()
    session_id = "s-ctx-1"
    initial = store.get(session_id)
    assert initial.has_context() is False

    store.update(session_id, category="coffee", period="last_week", intent="spend_by_category")
    updated = store.get(session_id)
    assert updated.category == "coffee"
    assert updated.period == "last_week"
    assert updated.intent == "spend_by_category"
    assert updated.has_context() is True


def test_chat_follow_up_uses_previous_category_context() -> None:
    session_id = "s-chat-followup"
    first = chat({"message": "Скільки витратила на каву минулого тижня?", "session_id": session_id})
    second = chat({"message": "А місяць?", "session_id": session_id})

    assert first["intent"] == "spend_by_category"
    assert first["resolved_category"] == "coffee"
    assert second["resolved_category"] == "coffee"
    assert second["resolved_period"] == "current_month"
