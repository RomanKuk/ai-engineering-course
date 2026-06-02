from __future__ import annotations

from app.main import run_eval


def test_eval_runner_returns_baseline_and_crew_summaries() -> None:
    result = run_eval({"max_cases": 5})
    assert "baseline" in result
    assert "crew" in result
    assert result["golden_set_size"] == 5

    baseline = result["baseline"]["summary"]
    crew = result["crew"]["summary"]

    for field in [
        "latency_p50",
        "latency_p95",
        "cost_per_task",
        "tokens_per_task",
        "success_rate",
        "tool_selection_accuracy",
        "groundedness",
        "inter_agent_overhead_pct",
        "intent_breakdown",
    ]:
        assert field in baseline
        assert field in crew

    assert isinstance(baseline["intent_breakdown"], dict)
    assert isinstance(crew["intent_breakdown"], dict)
