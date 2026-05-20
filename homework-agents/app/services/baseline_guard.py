from __future__ import annotations

import json
from pathlib import Path

from app.services.analytics import load_analytics, summary


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compare(actual: object, expected: object, tolerance: float, path: str = "root") -> None:
    if _is_number(actual) and _is_number(expected):
        if abs(float(actual) - float(expected)) > tolerance:
            raise AssertionError(f"Numeric mismatch at {path}: actual={actual}, expected={expected}")
        return

    if type(actual) is not type(expected):
        raise AssertionError(
            f"Type mismatch at {path}: actual_type={type(actual).__name__}, expected_type={type(expected).__name__}"
        )

    if isinstance(actual, dict):
        actual_keys = set(actual.keys())
        expected_keys = set(expected.keys())
        if actual_keys != expected_keys:
            raise AssertionError(
                f"Key mismatch at {path}: actual_only={sorted(actual_keys - expected_keys)}, "
                f"expected_only={sorted(expected_keys - actual_keys)}"
            )
        for key in sorted(actual_keys):
            _compare(actual[key], expected[key], tolerance, f"{path}.{key}")
        return

    if isinstance(actual, list):
        if len(actual) != len(expected):
            raise AssertionError(f"List length mismatch at {path}: actual={len(actual)}, expected={len(expected)}")
        for idx, (left, right) in enumerate(zip(actual, expected)):
            _compare(left, right, tolerance, f"{path}[{idx}]")
        return

    if actual != expected:
        raise AssertionError(f"Value mismatch at {path}: actual={actual}, expected={expected}")


def assert_summary_matches_baseline(csv_path: Path, baseline_summary_path: Path, tolerance: float = 1e-9) -> None:
    if not baseline_summary_path.exists():
        raise FileNotFoundError(
            f"Baseline summary file is missing: {baseline_summary_path}. "
            "Generate it first with scripts/build_summary.py"
        )

    baseline = json.loads(baseline_summary_path.read_text(encoding="utf-8"))
    current = summary(load_analytics(csv_path))
    _compare(current, baseline, tolerance=tolerance)
