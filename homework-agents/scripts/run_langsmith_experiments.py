from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from langsmith import Client
from langsmith.evaluation import evaluate

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.baseline_runtime import BaselineRuntime
from app.services.crew_runtime import CrewRuntime
from app.services.eval_runner import EvalRunner


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


def _load_golden_set(golden_path: Path, max_cases: Optional[int] = None) -> list[dict[str, Any]]:
    data = json.loads(golden_path.read_text(encoding="utf-8"))
    if max_cases is not None:
        return data[: max(1, max_cases)]
    return data


def _write_cases_csv(file_path: Path, cases: list[dict[str, Any]]) -> None:
    headers = [
        "id",
        "message",
        "expected_intent",
        "actual_intent",
        "expected_route",
        "actual_route",
        "latency_ms",
        "success",
        "tool_selection_ok",
        "groundedness",
        "required_tools",
        "tools_used",
    ]
    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for case in cases:
            row = dict(case)
            row["required_tools"] = "|".join(str(item) for item in case.get("required_tools", []))
            row["tools_used"] = "|".join(str(item) for item in case.get("tools_used", []))
            writer.writerow({key: row.get(key, "") for key in headers})


def _build_report_snippet(summary: dict[str, Any], artifact_dir: Path) -> str:
    baseline_summary = summary["local_eval"]["baseline"]["summary"]
    crew_summary = summary["local_eval"]["crew"]["summary"]
    lines = [
        "## LangSmith Run Snapshot",
        "",
        f"- Dataset: `{summary['dataset_name']}`",
        f"- Golden set size: `{summary['golden_set_size']}`",
        f"- Baseline experiment: `{summary['baseline_experiment']}`",
        f"- Crew experiment: `{summary['crew_experiment']}`",
        "",
        "### Local Summary Cross-Check",
        "",
        "| Metric | Baseline | Crew |",
        "| --- | ---: | ---: |",
        f"| latency_p50 | {baseline_summary['latency_p50']} | {crew_summary['latency_p50']} |",
        f"| latency_p95 | {baseline_summary['latency_p95']} | {crew_summary['latency_p95']} |",
        f"| cost_per_task | {baseline_summary['cost_per_task']} | {crew_summary['cost_per_task']} |",
        f"| tokens_per_task | {baseline_summary['tokens_per_task']} | {crew_summary['tokens_per_task']} |",
        f"| success_rate | {baseline_summary['success_rate']} | {crew_summary['success_rate']} |",
        f"| tool_selection_accuracy | {baseline_summary['tool_selection_accuracy']} | {crew_summary['tool_selection_accuracy']} |",
        f"| groundedness | {baseline_summary['groundedness']} | {crew_summary['groundedness']} |",
        f"| inter_agent_overhead_pct | {baseline_summary['inter_agent_overhead_pct']} | {crew_summary['inter_agent_overhead_pct']} |",
        "",
        "Artifacts:",
        f"- `{artifact_dir / 'langsmith_summary.json'}`",
        f"- `{artifact_dir / 'baseline_cases.csv'}`",
        f"- `{artifact_dir / 'crew_cases.csv'}`",
    ]
    return "\n".join(lines) + "\n"


def _write_artifacts(
    artifact_dir: Path,
    dataset_name: str,
    baseline_experiment: str,
    crew_experiment: str,
    local_eval: dict[str, Any],
) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "dataset_name": dataset_name,
        "golden_set_size": local_eval["golden_set_size"],
        "baseline_experiment": baseline_experiment,
        "crew_experiment": crew_experiment,
        "local_eval": local_eval,
    }

    summary_path = artifact_dir / "langsmith_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_cases_csv(artifact_dir / "baseline_cases.csv", local_eval["baseline"]["cases"])
    _write_cases_csv(artifact_dir / "crew_cases.csv", local_eval["crew"]["cases"])

    report_snippet = _build_report_snippet(summary, artifact_dir)
    (artifact_dir / "report_snippet.md").write_text(report_snippet, encoding="utf-8")
    return summary_path


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
    parser.add_argument(
        "--artifact-dir",
        default=str(ROOT / "var" / "langsmith"),
        help="Directory for JSON, CSV, and report snippet artifacts",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.langsmith_api_key:
        print("LANGSMITH_API_KEY is required.")
        return 1

    # Ensure the experiment process uses the configured LangSmith workspace and enables nested traces.
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_TRACING"] = "true"

    root = Path(__file__).resolve().parents[1]
    golden_path = root / "evals" / "golden_set.json"
    csv_path = root / "starter" / "data" / "transactions.csv"
    cases = _load_golden_set(golden_path, max_cases=args.max_cases)

    client = Client(api_key=settings.langsmith_api_key)
    _sync_dataset(client, dataset_name=args.dataset_name, cases=cases)

    baseline_runtime = BaselineRuntime(csv_path)
    crew_runtime = CrewRuntime(csv_path)
    eval_runner = EvalRunner(golden_path, baseline_runtime=baseline_runtime, crew_runtime=crew_runtime)

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

    local_eval = eval_runner.run(max_cases=args.max_cases)
    summary_path = _write_artifacts(
        artifact_dir=Path(args.artifact_dir),
        dataset_name=args.dataset_name,
        baseline_experiment=baseline_results.experiment_name,
        crew_experiment=crew_results.experiment_name,
        local_eval=local_eval,
    )

    print("LangSmith experiments completed.")
    print(f"Dataset: {args.dataset_name}")
    print(f"Baseline experiment: {baseline_results.experiment_name}")
    print(f"Crew experiment: {crew_results.experiment_name}")
    print(f"Summary artifact: {summary_path}")
    print("Open LangSmith project view to compare experiments side by side.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
