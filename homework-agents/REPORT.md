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

## LangSmith Run Snapshot

- Dataset: `personal-finance-golden-set`
- Golden set size: `15`
- Baseline experiment: `pfc-baseline-20260602-191428-6ab42343`
- Crew experiment: `pfc-crew-20260602-191428-c45bc11a`
- LangSmith compare view: `https://smith.langchain.com/o/45877eec-9828-48a4-bbe5-5395d744578a/datasets/c54ce81b-41c6-44af-a63d-8173a3eae5a3/compare?selectedSessions=b8288b5f-b8d7-4221-ac06-a73cb8c1fa05`

### Local Summary Cross-Check

| Metric | Baseline | Crew |
| --- | ---: | ---: |
| latency_p50 | 8.19 | 11.52 |
| latency_p95 | 16.28 | 32.94 |
| cost_per_task | 0.0 | 0.0 |
| tokens_per_task | 93.2 | 224.33 |
| success_rate | 0.9333 | 0.9333 |
| tool_selection_accuracy | 0.9333 | 0.9333 |
| groundedness | 0.579 | 0.6057 |
| inter_agent_overhead_pct | 0.0 | 73.4 |

Interpretation:

- Crew did not improve task success on the current 15-case golden set.
- Crew slightly improved groundedness (`0.6057` vs `0.579`) but at materially higher latency and token overhead.
- Baseline is currently the better production default for this deterministic analytics scope.
- Crew is justified only if we expand tasks where multi-step synthesis or richer decomposition materially improves answer quality.

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

Generated artifacts after the run:

- `var/langsmith/langsmith_summary.json`
- `var/langsmith/baseline_cases.csv`
- `var/langsmith/crew_cases.csv`
- `var/langsmith/report_snippet.md`

## Conclusion

The functional multi-agent comparison workflow is implemented locally and has been executed in LangSmith. On the current golden set, crew does not outperform baseline on success rate and introduces substantially more overhead, so the present recommendation is to keep baseline as the default production path and reserve crew for broader, more synthesis-heavy scenarios.