from __future__ import annotations

import json
import uuid

from app.schemas import ChatRequest, ChatResponse, ChatTrace
from app.services.intent_router import classify_intent
from app.services.session_context import SessionContextStore
from app.tools import (
    tool_compare_category_between_periods,
    tool_last_payment_by_merchant,
    tool_project_month_end_balance,
    tool_spend_by_category,
    tool_top_categories,
)


GUARDRAIL_INTENTS = {"fraud_escalation", "out_of_scope", "clarification_needed"}

CATEGORY_KEYWORDS = {
    "coffee": ["coffee", "кава", "каву"],
    "delivery": ["delivery", "доставка", "glovo", "bolt food", "uber eats", "доставк"],
    "subscriptions": ["subscriptions", "subscription", "підписк"],
    "groceries": ["groceries", "продукт"],
}

MERCHANT_KEYWORDS = [
    "netflix",
    "spotify",
    "apple one",
    "icloud storage",
    "sportlife",
    "booking.com",
    "aliexpress",
]


class CrewRuntime:
    def __init__(self, csv_path) -> None:
        self.csv_path = csv_path
        self.session_store = SessionContextStore()

    def handle_chat(self, body: dict) -> dict:
        request = ChatRequest.model_validate(body)
        message = str(request.message)
        session_id = str(request.session_id or uuid.uuid4())

        context = self.session_store.get(session_id)
        has_context = context.has_context()

        router = self._router_step(message=message, has_context=has_context, context=context)
        intent = router["intent"]
        intent_reason = router["intent_reason"]
        resolved_category = router["resolved_category"]
        resolved_period = router["resolved_period"]

        self.session_store.update(
            session_id,
            category=resolved_category,
            period=resolved_period,
            intent=intent,
        )
        updated_context = self.session_store.get(session_id)

        if intent in GUARDRAIL_INTENTS:
            metrics = self._crew_metrics(
                message=message,
                router=router,
                analyst={"agent": "analyst", "tools_used": [], "facts": {}},
                coach={"agent": "coach", "answer": self._guardrail_answer(intent)},
            )
            payload = {
                "architecture": "crew",
                "answer": self._guardrail_answer(intent),
                "echo": message,
                "session_id": session_id,
                "intent": intent,
                "intent_reason": intent_reason,
                "resolved_category": resolved_category,
                "resolved_period": resolved_period,
                "context": updated_context.to_dict(),
                "route": "guardrail",
                "guardrail_applied": True,
                "tools_used": [],
                "tool_outputs": {
                    "router": router,
                    "analyst": {},
                    "coach": {},
                    "crew_metrics": metrics,
                },
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

        analyst = self._analyst_step(
            intent=intent,
            message=message,
            resolved_category=resolved_category,
            resolved_period=resolved_period,
        )
        coach = self._coach_step(intent=intent, analyst=analyst)
        metrics = self._crew_metrics(message=message, router=router, analyst=analyst, coach=coach)

        payload = {
            "architecture": "crew",
            "answer": coach["answer"],
            "echo": message,
            "session_id": session_id,
            "intent": intent,
            "intent_reason": intent_reason,
            "resolved_category": resolved_category,
            "resolved_period": resolved_period,
            "context": updated_context.to_dict(),
            "route": "crew",
            "guardrail_applied": False,
            "tools_used": analyst["tools_used"],
            "tool_outputs": {
                "router": router,
                "analyst": analyst,
                "coach": coach,
                "crew_metrics": metrics,
            },
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

    def _router_step(self, *, message: str, has_context: bool, context) -> dict:
        result = classify_intent(message=message, has_context=has_context)
        category = self._extract_category(message) or context.category
        period = self._extract_period(message) or context.period
        return {
            "agent": "router",
            "intent": result.intent,
            "intent_reason": result.reason,
            "resolved_category": category,
            "resolved_period": period,
        }

    def _analyst_step(self, *, intent: str, message: str, resolved_category: str | None, resolved_period: str | None) -> dict:
        tools_used: list[str] = []
        facts: dict = {}

        if intent == "spend_by_category":
            category = resolved_category or "coffee"
            period = resolved_period or "current_month"
            facts["spend_by_category"] = tool_spend_by_category(self.csv_path, category=category, period=period)
            tools_used.append("spend_by_category")

        elif intent == "top_categories":
            period = resolved_period or "current_month"
            facts["top_categories"] = tool_top_categories(self.csv_path, period=period, limit=5)
            tools_used.append("top_categories")

        elif intent == "last_payment_by_merchant":
            merchant = self._extract_merchant(message) or "Netflix"
            facts["last_payment_by_merchant"] = tool_last_payment_by_merchant(self.csv_path, merchant=merchant)
            tools_used.append("last_payment_by_merchant")

        elif intent == "month_projection":
            facts["project_month_end_balance"] = tool_project_month_end_balance(self.csv_path)
            tools_used.append("project_month_end_balance")

        elif intent == "compare_periods":
            category = resolved_category or "delivery"
            facts["compare_category_between_periods"] = tool_compare_category_between_periods(
                self.csv_path,
                category=category,
                left_period="current_month",
                right_period="last_week",
            )
            tools_used.append("compare_category_between_periods")

        elif intent == "savings_advice":
            facts["top_categories"] = tool_top_categories(self.csv_path, period="current_month", limit=3)
            facts["project_month_end_balance"] = tool_project_month_end_balance(self.csv_path)
            tools_used.extend(["top_categories", "project_month_end_balance"])

        return {
            "agent": "analyst",
            "tools_used": tools_used,
            "facts": facts,
        }

    def _coach_step(self, *, intent: str, analyst: dict) -> dict:
        facts = analyst.get("facts", {})

        if intent == "spend_by_category" and "spend_by_category" in facts:
            item = facts["spend_by_category"]
            answer = (
                f"Crew result: you spent ${item['total']:.2f} on {item['category']} in {item['period'].replace('_', ' ')} "
                f"({item['start']} to {item['end']})."
            )
        elif intent == "top_categories" and "top_categories" in facts:
            rows = facts["top_categories"].get("items", [])
            if rows:
                top = "; ".join(f"{idx + 1}. {it['category']} ${float(it['total']):.2f}" for idx, it in enumerate(rows))
                answer = f"Crew top categories: {top}."
            else:
                answer = "Crew could not find spending rows for the requested period."
        elif intent == "last_payment_by_merchant" and "last_payment_by_merchant" in facts:
            row = facts["last_payment_by_merchant"]
            if row.get("found"):
                item = row["item"]
                answer = f"Crew found last payment for {item['merchant']} on {item['date']} for ${abs(float(item['amount'])):.2f}."
            else:
                answer = "Crew could not find that merchant in your transactions."
        elif intent == "month_projection" and "project_month_end_balance" in facts:
            row = facts["project_month_end_balance"]
            answer = (
                f"Crew projection for {row['month']}: income ${row['income']:.2f}, projected spending "
                f"${row['projected_spending']:.2f}, projected balance ${row['projected_balance']:.2f}."
            )
        elif intent == "compare_periods" and "compare_category_between_periods" in facts:
            row = facts["compare_category_between_periods"]
            answer = (
                f"Crew comparison for {row['category']}: current month ${row['left']['total']:.2f}, "
                f"last week ${row['right']['total']:.2f}, delta ${row['delta']:.2f}."
            )
        elif intent == "savings_advice" and "top_categories" in facts and "project_month_end_balance" in facts:
            top = ", ".join(
                f"{item['category']} (${float(item['total']):.2f})" for item in facts["top_categories"].get("items", [])
            )
            proj = facts["project_month_end_balance"]
            answer = (
                f"Crew advice: prioritize reducing {top}. Projected month-end balance is "
                f"${proj['projected_balance']:.2f}."
            )
        else:
            answer = "Crew can help with spending, categories, merchant payments, projections, and comparisons."

        return {
            "agent": "coach",
            "answer": answer,
        }

    def _crew_metrics(self, *, message: str, router: dict, analyst: dict, coach: dict) -> dict:
        # Very rough token estimate to make inter-agent overhead observable in traces.
        router_text = json.dumps(router, ensure_ascii=False)
        analyst_text = json.dumps(analyst, ensure_ascii=False)
        coach_text = json.dumps(coach, ensure_ascii=False)

        router_tokens = max(1, len(router_text) // 4)
        analyst_tokens = max(1, len(analyst_text) // 4)
        coach_tokens = max(1, len(coach_text) // 4)

        message_tokens = max(1, len(message) // 4)
        answer_tokens = max(1, len(str(coach.get("answer", ""))) // 4)
        internal_tokens = router_tokens + analyst_tokens
        total_tokens = internal_tokens + message_tokens + answer_tokens
        overhead_pct = round((internal_tokens / max(1, total_tokens)) * 100, 2)

        return {
            "token_breakdown_by_agent": {
                "router": router_tokens,
                "analyst": analyst_tokens,
                "coach": coach_tokens,
            },
            "inter_agent_overhead_pct": overhead_pct,
            "cost_breakdown_by_agent": {
                "router": 0.0,
                "analyst": 0.0,
                "coach": 0.0,
            },
        }

    def _extract_category(self, message: str) -> str | None:
        text = message.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return category
        return None

    def _extract_period(self, message: str) -> str | None:
        text = message.lower().strip()
        if "last week" in text or "минулого тижня" in text or "минулий тиждень" in text:
            return "last_week"
        if (
            "this month" in text
            or "цього місяця" in text
            or text == "місяць"
            or text.startswith("а місяц")
            or text.startswith("and for the month")
            or text.startswith("what about the month")
        ):
            return "current_month"
        return None

    def _extract_merchant(self, message: str) -> str | None:
        text = message.lower()
        for merchant in MERCHANT_KEYWORDS:
            if merchant in text:
                return merchant
        return None

    def _guardrail_answer(self, intent: str) -> str:
        if intent == "fraud_escalation":
            return (
                "This looks like a potentially disputed transaction. I cannot block cards or issue chargebacks directly. "
                "Please contact bank support immediately, and I can still show your latest card transactions for review."
            )
        if intent == "out_of_scope":
            return (
                "I cannot help with investing or buying assets. I can analyze your spending, subscriptions, cash flow, "
                "and suggest concrete savings actions based on your transactions."
            )
        if intent == "clarification_needed":
            return "Please clarify which category or merchant you mean so I can continue the analysis."
        return "Request blocked by guardrails."
