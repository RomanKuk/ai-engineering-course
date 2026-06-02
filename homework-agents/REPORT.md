# Personal Finance Coach Report

## Implemented

- Shared `/chat` endpoint with `baseline` and `crew` architectures.
- Single-agent baseline with deterministic tool calls over the provided transaction CSV.
- Crew runtime with 3 specialized roles: router, analyst, coach.
- Guardrails for `fraud_escalation`, `out_of_scope`, and `clarification_needed`.
- Multi-turn context resolution for category and period follow-ups.
- Golden set with 15 tasks in `evals/golden_set.json`.
- Local evaluation runner with side-by-side baseline vs crew summaries.
- Streamlit UI with chat and eval tabs, trace view, and downloads.
- Optional LangSmith tracing hooks controlled by `LANGSMITH_TRACING`.
- LangSmith experiment runner script: `scripts/run_langsmith_experiments.py`.

## Current Metrics Snapshot

These values come from the local evaluator and are the numbers currently surfaced in the UI:

- `latency_p50`
- `latency_p95`
- `cost_per_task`
- `tokens_per_task`
- `success_rate`
- `tool_selection_accuracy`
- `groundedness`
- `inter_agent_overhead_pct`
- `cost_breakdown_by_agent`

The evaluator also reports per-intent breakdowns for:

- `count`
- `success_rate`
- `tool_selection_accuracy`
- `groundedness`
- `avg_latency_ms`

## What Is Still Missing

The implementation now includes a LangSmith dataset/experiment runner. The remaining step is operational: run the script with a valid API key and attach experiment links/screenshots plus final interpretation in this report.

## How To Run

```bash
uvicorn app.main:app --reload
streamlit run ui/app.py
python -m pytest -q
```

To run the eval endpoint manually:

```bash
curl -X POST http://127.0.0.1:8000/eval/run -H "Content-Type: application/json" -d "{\"max_cases\": 15}"
```

To enable LangSmith tracing:

- Set `LANGSMITH_TRACING=true`
- Set `LANGSMITH_API_KEY`
- Keep `LANGSMITH_PROJECT=personal-finance-coach`

To run LangSmith experiments:

```bash
python scripts/run_langsmith_experiments.py --dataset-name personal-finance-golden-set --max-cases 15
```

## Conclusion

The functional multi-agent comparison workflow is implemented locally and includes a LangSmith experiment runner. Final submission readiness depends on executing that runner in your LangSmith workspace and adding the resulting experiment evidence to this report.