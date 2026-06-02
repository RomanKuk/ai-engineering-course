from __future__ import annotations

from contextlib import nullcontext

from langsmith import tracing_context

from app.core.config import get_settings


def langsmith_context(*, run_name: str, tags: list[str] | None = None, metadata: dict | None = None):
    settings = get_settings()
    if not settings.langsmith_tracing:
        return nullcontext()

    merged_tags = ["personal-finance-coach", run_name]
    if tags:
        merged_tags.extend(tags)
    return tracing_context(
        project_name=settings.langsmith_project,
        tags=merged_tags,
        metadata={**(metadata or {}), "run_name": run_name},
        enabled=True,
    )