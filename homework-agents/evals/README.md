# Evals

This folder contains the golden set for local and LangSmith experiments.

## Files

- `golden_set.json`: 15-case evaluation set used for baseline vs crew comparison.

## Run LangSmith Experiments

Use the script below to sync the golden set into LangSmith and run two experiments:

- baseline architecture
- crew architecture

Command:

```bash
python scripts/run_langsmith_experiments.py --dataset-name personal-finance-golden-set
```

Optional:

```bash
python scripts/run_langsmith_experiments.py --dataset-name personal-finance-golden-set --max-cases 15
```

Required env vars:

- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT` (defaults to `personal-finance-coach` from app settings)
