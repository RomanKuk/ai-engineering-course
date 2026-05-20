from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(default="")
    architecture: Literal["baseline", "crew"] = "baseline"
    session_id: Optional[str] = None


class ChatTrace(BaseModel):
    intent: str
    intent_reason: str
    route: Literal["baseline", "guardrail", "crew"]
    guardrail_applied: bool
    resolved_category: Optional[str] = None
    resolved_period: Optional[str] = None
    context: Dict[str, Optional[str]] = Field(default_factory=dict)
    tools_used: List[str] = Field(default_factory=list)
    tool_outputs: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    architecture: str
    answer: str
    echo: str
    session_id: str
    intent: str
    intent_reason: str
    resolved_category: Optional[str] = None
    resolved_period: Optional[str] = None
    context: Dict[str, Optional[str]] = Field(default_factory=dict)
    route: Literal["baseline", "guardrail", "crew"]
    guardrail_applied: bool
    tools_used: List[str] = Field(default_factory=list)
    tool_outputs: Dict[str, Any] = Field(default_factory=dict)
    trace: ChatTrace
