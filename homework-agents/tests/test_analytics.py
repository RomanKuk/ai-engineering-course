from __future__ import annotations

from pathlib import Path

from app.services.analytics import current_month_window, last_week_window, load_analytics, summary


def test_anchor_date_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    analytics = load_analytics(root / "starter" / "data" / "transactions.csv")
    assert analytics.anchor_date is not None


def test_time_windows_ordered() -> None:
    root = Path(__file__).resolve().parents[1]
    analytics = load_analytics(root / "starter" / "data" / "transactions.csv")
    cm_start, cm_end = current_month_window(analytics.anchor_date)
    lw_start, lw_end = last_week_window(analytics.anchor_date)
    assert cm_start <= cm_end
    assert lw_start <= lw_end


def test_summary_has_expected_keys() -> None:
    root = Path(__file__).resolve().parents[1]
    analytics = load_analytics(root / "starter" / "data" / "transactions.csv")
    result = summary(analytics)
    assert "anchor_date" in result
    assert "coffee_last_week" in result
    assert "top5_current_month" in result
    assert isinstance(result["top5_current_month"], list)
