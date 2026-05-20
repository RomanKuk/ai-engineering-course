from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any, Optional


def _flatten_numbers(value: Any) -> list[float]:
    numbers: list[float] = []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numbers.append(float(value))
    elif isinstance(value, dict):
        for item in value.values():
            numbers.extend(_flatten_numbers(item))
    elif isinstance(value, list):
        for item in value:
            numbers.extend(_flatten_numbers(item))
    return numbers


def _extract_answer_numbers(answer: str) -> list[float]:
    import re

    values = re.findall(r"\d+(?:\.\d+)?", answer)
    return [float(v) for v in values]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * p))
    return ordered[idx]


class EvalRunner:
    def __init__(self, golden_path: Path, baseline_runtime, crew_runtime) -> None:
        self.golden_path = golden_path
        self.baseline_runtime = baseline_runtime
        self.crew_runtime = crew_runtime

    def load_golden_set(self) -> list[dict]:
        return json.loads(self.golden_path.read_text(encoding="utf-8"))

    def run(self, max_cases: Optional[int] = None) -> dict:
        cases = self.load_golden_set()
        if max_cases is not None:
            cases = cases[: max(1, max_cases)]

        baseline = self._run_architecture("baseline", cases)
        crew = self._run_architecture("crew", cases)
        return {
            "golden_set_size": len(cases),
            "baseline": baseline,
            "crew": crew,
        }

    def _run_architecture(self, architecture: str, cases: list[dict]) -> dict:
        runtime = self.baseline_runtime if architecture == "baseline" else self.crew_runtime

        results: list[dict] = []
        latencies: list[float] = []
        token_estimates: list[float] = []
        success_scores: list[float] = []
        tool_scores: list[float] = []
        grounded_scores: list[float] = []
        overhead_values: list[float] = []
        agent_costs: dict[str, list[float]] = {"router": [], "analyst": [], "coach": []}
        intent_stats: dict[str, dict[str, float]] = {}

        for case in cases:
            started = perf_counter()
            response = runtime.handle_chat({"message": case["message"], "architecture": architecture})
            latency_ms = (perf_counter() - started) * 1000.0
            latencies.append(latency_ms)

            required_tools = case.get("required_tools", [])
            used_tools = response.get("tools_used", [])
            tool_ok = all(tool in used_tools for tool in required_tools)
            tool_scores.append(1.0 if tool_ok else 0.0)

            intent_ok = response.get("intent") == case.get("expected_intent")
            route_expected = case.get("expected_route")
            route_ok = True if not route_expected else response.get("route") == route_expected
            success_scores.append(1.0 if (intent_ok and route_ok and tool_ok) else 0.0)

            expected_intent = str(case.get("expected_intent", "unknown"))
            stats = intent_stats.setdefault(
                expected_intent,
                {
                    "count": 0.0,
                    "success_sum": 0.0,
                    "tool_sum": 0.0,
                    "grounded_sum": 0.0,
                    "latency_sum": 0.0,
                },
            )
            stats["count"] += 1.0
            stats["success_sum"] += success_scores[-1]
            stats["tool_sum"] += 1.0 if tool_ok else 0.0

            answer_numbers = _extract_answer_numbers(response.get("answer", ""))
            tool_numbers = _flatten_numbers(response.get("tool_outputs", {}))
            if response.get("guardrail_applied"):
                grounded_scores.append(1.0)
            elif not answer_numbers:
                grounded_scores.append(0.0)
            elif not tool_numbers:
                grounded_scores.append(0.0)
            else:
                matches = 0
                for num in answer_numbers:
                    if any(abs(num - t) < 0.01 for t in tool_numbers):
                        matches += 1
                grounded_scores.append(matches / max(1, len(answer_numbers)))
            stats["grounded_sum"] += grounded_scores[-1]
            stats["latency_sum"] += latency_ms

            message = case.get("message", "")
            token_est = (len(message) + len(response.get("answer", "")) + len(json.dumps(response.get("tool_outputs", {})))) / 4.0
            token_estimates.append(token_est)

            crew_metrics = response.get("tool_outputs", {}).get("crew_metrics", {})
            if isinstance(crew_metrics, dict):
                overhead_values.append(float(crew_metrics.get("inter_agent_overhead_pct", 0.0)))
                costs = crew_metrics.get("cost_breakdown_by_agent", {})
                if isinstance(costs, dict):
                    for agent in agent_costs:
                        agent_costs[agent].append(float(costs.get(agent, 0.0)))

            results.append(
                {
                    "id": case.get("id"),
                    "message": case.get("message"),
                    "expected_intent": case.get("expected_intent"),
                    "actual_intent": response.get("intent"),
                    "expected_route": case.get("expected_route"),
                    "actual_route": response.get("route"),
                    "required_tools": required_tools,
                    "tools_used": used_tools,
                    "latency_ms": round(latency_ms, 2),
                    "success": success_scores[-1] == 1.0,
                    "tool_selection_ok": tool_ok,
                    "groundedness": round(grounded_scores[-1], 4),
                }
            )

        summary = {
            "tasks": len(cases),
            "latency_p50": round(_percentile(latencies, 0.5), 2),
            "latency_p95": round(_percentile(latencies, 0.95), 2),
            "cost_per_task": 0.0,
            "tokens_per_task": round(sum(token_estimates) / max(1, len(token_estimates)), 2),
            "success_rate": round(sum(success_scores) / max(1, len(success_scores)), 4),
            "tool_selection_accuracy": round(sum(tool_scores) / max(1, len(tool_scores)), 4),
            "groundedness": round(sum(grounded_scores) / max(1, len(grounded_scores)), 4),
            "inter_agent_overhead_pct": round(sum(overhead_values) / max(1, len(overhead_values)), 2),
            "cost_breakdown_by_agent": {
                key: round(sum(values) / max(1, len(values)), 6) for key, values in agent_costs.items()
            },
            "intent_breakdown": {
                intent: {
                    "count": int(values["count"]),
                    "success_rate": round(values["success_sum"] / max(1.0, values["count"]), 4),
                    "tool_selection_accuracy": round(values["tool_sum"] / max(1.0, values["count"]), 4),
                    "groundedness": round(values["grounded_sum"] / max(1.0, values["count"]), 4),
                    "avg_latency_ms": round(values["latency_sum"] / max(1.0, values["count"]), 2),
                }
                for intent, values in intent_stats.items()
            },
        }
        return {
            "summary": summary,
            "cases": results,
        }
