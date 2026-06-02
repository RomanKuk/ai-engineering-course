from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from langsmith import Client
from langsmith.evaluation import evaluate

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.baseline_runtime import BaselineRuntime
from app.services.crew_runtime import CrewRuntime


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

    values = re.findall(r"\d+(?:\.\d+)?", answer or "")
    return [float(v) for v in values]


def _load_golden_set(golden_path: Path, max_cases: int | None = None) -> list[dict[str, Any]]:
    data = json.loads(golden_path.read_text(encoding="utf-8"))
    if max_cases is not None:
        return data[: max(1, max_cases)]
    return data


def _sync_dataset(client: Client, dataset_name: str, cases: list[dict[str, Any]]) -> None:
    if client.has_dataset(dataset_name=dataset_name):
        client.delete_dataset(dataset_name=dataset_name)

    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description="Personal Finance Coach golden set for baseline vs crew experiments",
    )

    examples = []
    for case in cases:
        examples.append(
            {
                "inputs": {
                    "message": case["message"],
                    "case_id": case.get("id"),
                },
                "outputs": {
                    "expected_intent": case.get("expected_intent"),
                    "expected_route": case.get("expected_route"),
                    "required_tools": case.get("required_tools", []),
                },
                "metadata": {
                    "case_id": case.get("id"),
                },
            }
        )

    client.create_examples(dataset_id=dataset.id, examples=examples)


def _make_target(runtime, architecture: str):
    def _target(inputs: dict[str, Any]) -> dict[str, Any]:
        message = str(inputs.get("message", ""))
        case_id = str(inputs.get("case_id", ""))
        response = runtime.handle_chat(
            {
                "message": message,
                "architecture": architecture,
                "session_id": f"langsmith-{architecture}-{case_id}",
            }
        )
        return {
            "answer": response.get("answer", ""),
            "intent": response.get("intent", ""),
            "route": response.get("route", ""),
            "guardrail_applied": bool(response.get("guardrail_applied", False)),
            "tools_used": response.get("tools_used", []),
            "tool_outputs": response.get("tool_outputs", {}),
        }

    return _target


def _intent_match(run, example) -> dict[str, Any]:
    pred = (run.outputs or {}).get("intent")
    expected = (example.outputs or {}).get("expected_intent")
    score = 1.0 if pred == expected else 0.0
    return {"key": "intent_match", "score": score}


def _route_match(run, example) -> dict[str, Any]:
    pred = (run.outputs or {}).get("route")
    expected = (example.outputs or {}).get("expected_route")
    if not expected:
        score = 1.0
    else:
        score = 1.0 if pred == expected else 0.0
    return {"key": "route_match", "score": score}


def _tool_selection_accuracy(run, example) -> dict[str, Any]:
    used = set((run.outputs or {}).get("tools_used", []) or [])
    required = set((example.outputs or {}).get("required_tools", []) or [])
    score = 1.0 if required.issubset(used) else 0.0
    return {"key": "tool_selection_accuracy", "score": score}


def _groundedness(run, _example) -> dict[str, Any]:
    outputs = run.outputs or {}
    if outputs.get("guardrail_applied"):
        return {"key": "groundedness", "score": 1.0}

    answer_numbers = _extract_answer_numbers(str(outputs.get("answer", "")))
    tool_numbers = _flatten_numbers(outputs.get("tool_outputs", {}))
    if not answer_numbers or not tool_numbers:
        return {"key": "groundedness", "score": 0.0}

    matches = 0
    for num in answer_numbers:
        if any(abs(num - t) < 0.01 for t in tool_numbers):
            matches += 1
    score = matches / max(1, len(answer_numbers))
    return {"key": "groundedness", "score": float(score)}


def _success_rate(run, example) -> dict[str, Any]:
    intent_score = _intent_match(run, example)["score"]
    route_score = _route_match(run, example)["score"]
    tool_score = _tool_selection_accuracy(run, example)["score"]
    score = 1.0 if (intent_score == 1.0 and route_score == 1.0 and tool_score == 1.0) else 0.0
    return {"key": "success_rate", "score": score}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LangSmith experiments for baseline vs crew")
    parser.add_argument("--dataset-name", default="personal-finance-golden-set", help="LangSmith dataset name")
    parser.add_argument("--max-cases", type=int, default=None, help="Limit number of cases")
    args = parser.parse_args()

    if not os.getenv("LANGSMITH_API_KEY"):
        print("LANGSMITH_API_KEY is required.")
        return 1

    root = Path(__file__).resolve().parents[1]
    golden_path = root / "evals" / "golden_set.json"
    csv_path = root / "starter" / "data" / "transactions.csv"
    cases = _load_golden_set(golden_path, max_cases=args.max_cases)

    client = Client()
    _sync_dataset(client, dataset_name=args.dataset_name, cases=cases)

    baseline_runtime = BaselineRuntime(csv_path)
    crew_runtime = CrewRuntime(csv_path)

    evaluators = [
        _intent_match,
        _route_match,
        _tool_selection_accuracy,
        _groundedness,
        _success_rate,
    ]

    now = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    baseline_prefix = f"pfc-baseline-{now}"
    crew_prefix = f"pfc-crew-{now}"

    baseline_results = evaluate(
        _make_target(baseline_runtime, "baseline"),
        data=args.dataset_name,
        evaluators=evaluators,
        experiment_prefix=baseline_prefix,
        description="Baseline experiment over personal finance golden set",
        metadata={"architecture": "baseline", "dataset": args.dataset_name},
        client=client,
    )
    baseline_results.wait()

    crew_results = evaluate(
        _make_target(crew_runtime, "crew"),
        data=args.dataset_name,
        evaluators=evaluators,
        experiment_prefix=crew_prefix,
        description="Crew experiment over personal finance golden set",
        metadata={"architecture": "crew", "dataset": args.dataset_name},
        client=client,
    )
    crew_results.wait()

    print("LangSmith experiments completed.")
    print(f"Dataset: {args.dataset_name}")
    print(f"Baseline experiment: {baseline_results.experiment_name}")
    print(f"Crew experiment: {crew_results.experiment_name}")
    print("Open LangSmith project view to compare experiments side by side.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
