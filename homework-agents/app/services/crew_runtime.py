from __future__ import annotations

import uuid

from app.schemas import ChatRequest, ChatResponse, ChatTrace


class CrewRuntime:
    def handle_chat(self, body: dict) -> dict:
        request = ChatRequest.model_validate(body)
        message = str(request.message)
        session_id = str(request.session_id or uuid.uuid4())

        payload = {
            "architecture": "crew",
            "answer": (
                "Crew architecture placeholder is active. Baseline is fully implemented; "
                "crew orchestration will be added in the next phase."
            ),
            "echo": message,
            "session_id": session_id,
            "intent": "crew_placeholder",
            "intent_reason": "crew_not_implemented",
            "resolved_category": None,
            "resolved_period": None,
            "context": {},
            "route": "crew",
            "guardrail_applied": False,
            "tools_used": [],
            "tool_outputs": {},
        }

        payload["trace"] = ChatTrace(
            intent=payload["intent"],
            intent_reason=payload["intent_reason"],
            route=payload["route"],
            guardrail_applied=payload["guardrail_applied"],
            resolved_category=payload["resolved_category"],
            resolved_period=payload["resolved_period"],
            context=payload["context"],
            tools_used=payload["tools_used"],
            tool_outputs=payload["tool_outputs"],
        ).model_dump()
        return ChatResponse.model_validate(payload).model_dump()
