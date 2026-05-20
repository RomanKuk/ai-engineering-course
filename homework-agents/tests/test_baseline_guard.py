from __future__ import annotations

from pathlib import Path

from app.services.baseline_guard import assert_summary_matches_baseline


def test_current_summary_matches_frozen_baseline() -> None:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "starter" / "data" / "transactions.csv"
    baseline_path = root / "var" / "baseline_summary.json"
    assert_summary_matches_baseline(csv_path=csv_path, baseline_summary_path=baseline_path)
