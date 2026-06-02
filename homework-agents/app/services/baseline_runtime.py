from __future__ import annotations

from pathlib import Path
import uuid

from app.schemas import ChatRequest, ChatResponse, ChatTrace
from app.services.observability import langsmith_context
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


class BaselineRuntime:
    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self.session_store = SessionContextStore()

    def handle_chat(self, body: dict) -> dict:
        request = ChatRequest.model_validate(body)
        with langsmith_context(
            run_name="baseline.chat",
            tags=["baseline"],
            metadata={"architecture": request.architecture},
        ):
            architecture = request.architecture
            message = str(request.message)
            session_id = str(request.session_id or uuid.uuid4())

            context = self.session_store.get(session_id)
            has_context = context.has_context()
            intent = classify_intent(message=message, has_context=has_context)

            extracted_category = self._extract_category(message)
            extracted_period = self._extract_period(message)
            resolved_category = extracted_category or context.category
            resolved_period = extracted_period or context.period

            self.session_store.update(
                session_id,
                category=resolved_category,
                period=resolved_period,
                intent=intent.intent,
            )
            updated_context = self.session_store.get(session_id)

            if intent.intent in GUARDRAIL_INTENTS:
                payload = {
                    "architecture": architecture,
                    "answer": self._guardrail_answer(intent.intent),
                    "echo": message,
                    "session_id": session_id,
                    "intent": intent.intent,
                    "intent_reason": intent.reason,
                    "resolved_category": resolved_category,
                    "resolved_period": resolved_period,
                    "context": updated_context.to_dict(),
                    "route": "guardrail",
                    "guardrail_applied": True,
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

            answer, tools_used, tool_outputs = self._baseline_response(
                intent=intent.intent,
                message=message,
                resolved_category=resolved_category,
                resolved_period=resolved_period,
            )

            payload = {
                "architecture": architecture,
                "answer": answer,
                "echo": message,
                "session_id": session_id,
                "intent": intent.intent,
                "intent_reason": intent.reason,
                "resolved_category": resolved_category,
                "resolved_period": resolved_period,
                "context": updated_context.to_dict(),
                "route": "baseline",
                "guardrail_applied": False,
                "tools_used": tools_used,
                "tool_outputs": tool_outputs,
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

    def _baseline_response(
        self,
        *,
        intent: str,
        message: str,
        resolved_category: str | None,
        resolved_period: str | None,
    ) -> tuple[str, list[str], dict]:
        tools_used: list[str] = []
        outputs: dict = {}

        if intent == "spend_by_category":
            category = resolved_category or "coffee"
            period = resolved_period or "current_month"
            result = tool_spend_by_category(self.csv_path, category=category, period=period)
            tools_used.append("spend_by_category")
            outputs["spend_by_category"] = result
            answer = (
                f"You spent ${result['total']:.2f} on {category} in {period.replace('_', ' ')} "
                f"({result['start']} to {result['end']})."
            )
            return answer, tools_used, outputs

        if intent == "top_categories":
            period = resolved_period or "current_month"
            result = tool_top_categories(self.csv_path, period=period, limit=5)
            tools_used.append("top_categories")
            outputs["top_categories"] = result
            if result["items"]:
                top = "; ".join(
                    f"{idx + 1}. {item['category']} ${float(item['total']):.2f}"
                    for idx, item in enumerate(result["items"])
                )
                answer = f"Top categories for {period.replace('_', ' ')}: {top}."
            else:
                answer = f"No spending records found for {period.replace('_', ' ')}."
            return answer, tools_used, outputs

        if intent == "last_payment_by_merchant":
            merchant = self._extract_merchant(message) or "Netflix"
            result = tool_last_payment_by_merchant(self.csv_path, merchant=merchant)
            tools_used.append("last_payment_by_merchant")
            outputs["last_payment_by_merchant"] = result
            if result["found"]:
                item = result["item"]
                answer = (
                    f"Last payment for {item['merchant']} was {item['date']} for ${abs(float(item['amount'])):.2f} "
                    f"in category {item['category']}."
                )
            else:
                answer = f"I could not find payments for merchant '{merchant}'."
            return answer, tools_used, outputs

        if intent == "savings_advice":
            top = tool_top_categories(self.csv_path, period="current_month", limit=3)
            proj = tool_project_month_end_balance(self.csv_path)
            tools_used.extend(["top_categories", "project_month_end_balance"])
            outputs["top_categories"] = top
            outputs["project_month_end_balance"] = proj
            top_line = ", ".join(
                f"{item['category']} (${float(item['total']):.2f})" for item in top.get("items", [])
            )
            answer = (
                "Based on your latest data, biggest spend buckets this month are "
                f"{top_line}. Projected month-end balance is ${proj['projected_balance']:.2f}. "
                "Start by reducing the top discretionary category by 20% to create immediate savings."
            )
            return answer, tools_used, outputs

        if intent == "compare_periods":
            category = resolved_category or "delivery"
            result = tool_compare_category_between_periods(
                self.csv_path,
                category=category,
                left_period="current_month",
                right_period="last_week",
            )
            tools_used.append("compare_category_between_periods")
            outputs["compare_category_between_periods"] = result
            answer = (
                f"For {category}, current month total is ${result['left']['total']:.2f} vs "
                f"${result['right']['total']:.2f} last week (delta ${result['delta']:.2f})."
            )
            return answer, tools_used, outputs

        if intent == "month_projection":
            result = tool_project_month_end_balance(self.csv_path)
            tools_used.append("project_month_end_balance")
            outputs["project_month_end_balance"] = result
            answer = (
                f"For {result['month']}, income is ${result['income']:.2f}, projected spending is "
                f"${result['projected_spending']:.2f}, projected balance is ${result['projected_balance']:.2f}."
            )
            return answer, tools_used, outputs

        answer = (
            "I can help with spending by category, top categories, last merchant payment, savings ideas, "
            "period comparisons, and month-end projection."
        )
        return answer, tools_used, outputs
