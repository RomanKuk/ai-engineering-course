from __future__ import annotations

from dataclasses import dataclass
import re


INTENTS = {
    "spend_by_category",
    "top_categories",
    "last_payment_by_merchant",
    "savings_advice",
    "compare_periods",
    "month_projection",
    "fraud_escalation",
    "out_of_scope",
    "clarification_needed",
    "fallback",
}


FRAUD_PATTERNS = [
    r"fraud",
    r"unauthori[sz]ed",
    r"chargeback",
    r"dispute",
    r"шахрай",
    r"підозр",
    r"не\s+роби(в|ла)",
    r"did\s+not\s+make",
    r"i\s+didn['’]?t\s+make",
]

OUT_OF_SCOPE_PATTERNS = [
    r"buy\s+stocks?",
    r"invest",
    r"trading?",
    r"crypto",
    r"купи.*акц",
    r"інвест",
    r"крипт",
    r"трейд",
]

CLARIFY_FOLLOWUP_PATTERNS = [
    r"^а\s+місяц",
    r"^а\s+за\s+місяц",
    r"^and\s+for\s+the\s+month",
    r"^what\s+about\s+the\s+month",
]


@dataclass
class IntentResult:
    intent: str
    reason: str


def classify_intent(message: str, has_context: bool = True) -> IntentResult:
    text = message.strip().lower()

    if _matches_any(text, FRAUD_PATTERNS):
        return IntentResult(intent="fraud_escalation", reason="fraud_pattern")

    if _matches_any(text, OUT_OF_SCOPE_PATTERNS):
        return IntentResult(intent="out_of_scope", reason="out_of_scope_pattern")

    if _matches_any(text, CLARIFY_FOLLOWUP_PATTERNS) and not has_context:
        return IntentResult(intent="clarification_needed", reason="follow_up_without_context")

    if ("top" in text and "categor" in text) or ("топ" in text and "категор" in text):
        return IntentResult(intent="top_categories", reason="top_categories_pattern")

    if (
        "last payment" in text
        or "остан" in text and ("payment" in text or "плат" in text)
        or "netflix" in text
    ):
        return IntentResult(intent="last_payment_by_merchant", reason="last_payment_pattern")

    if "зеконом" in text or "save" in text:
        return IntentResult(intent="savings_advice", reason="savings_pattern")

    if "порівня" in text or "compare" in text:
        return IntentResult(intent="compare_periods", reason="compare_pattern")

    if ("закрит" in text and "плюс" in text) or ("close" in text and "plus" in text):
        return IntentResult(intent="month_projection", reason="projection_pattern")

    if "скільки" in text or "how much" in text or text == "місяць" or text.startswith("а місяц"):
        return IntentResult(intent="spend_by_category", reason="spend_pattern")

    return IntentResult(intent="fallback", reason="no_match")


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
