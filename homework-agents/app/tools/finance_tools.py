from __future__ import annotations

from calendar import monthrange
from pathlib import Path

from app.services.analytics import (
    current_month_window,
    last_week_window,
    load_analytics,
    spend_by_category,
    top_categories,
)


def list_tools() -> list[dict]:
    return [
        {"name": "spend_by_category", "args": ["category", "period"]},
        {"name": "top_categories", "args": ["period", "limit"]},
        {"name": "last_payment_by_merchant", "args": ["merchant"]},
        {"name": "recent_credit_card_transactions", "args": ["limit"]},
        {"name": "compare_category_between_periods", "args": ["category", "left_period", "right_period"]},
        {"name": "project_month_end_balance", "args": []},
    ]


def _window_for_period(anchor, period: str):
    value = period.strip().lower()
    if value == "current_month":
        return current_month_window(anchor)
    if value == "last_week":
        return last_week_window(anchor)
    raise ValueError(f"Unsupported period '{period}'. Allowed: current_month, last_week")


def tool_spend_by_category(csv_path: Path, category: str, period: str = "current_month") -> dict:
    analytics = load_analytics(csv_path)
    start, end = _window_for_period(analytics.anchor_date, period)
    total = spend_by_category(analytics, category=category, start=start, end=end)
    return {
        "tool": "spend_by_category",
        "category": category,
        "period": period,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "total": round(total, 2),
    }


def tool_top_categories(csv_path: Path, period: str = "current_month", limit: int = 5) -> dict:
    analytics = load_analytics(csv_path)
    start, end = _window_for_period(analytics.anchor_date, period)
    rows = top_categories(analytics, start=start, end=end, k=limit)
    return {
        "tool": "top_categories",
        "period": period,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "limit": int(limit),
        "items": rows,
    }


def tool_last_payment_by_merchant(csv_path: Path, merchant: str) -> dict:
    analytics = load_analytics(csv_path)
    rows = analytics.df[analytics.df["merchant"].str.lower() == merchant.lower()].copy()
    if rows.empty:
        return {
            "tool": "last_payment_by_merchant",
            "merchant": merchant,
            "found": False,
            "item": None,
        }
    row = rows.sort_values("date_parsed", ascending=False).iloc[0]
    return {
        "tool": "last_payment_by_merchant",
        "merchant": merchant,
        "found": True,
        "item": {
            "date": str(row["date"]),
            "merchant": str(row["merchant"]),
            "amount": float(row["amount"]),
            "category": str(row["category"]),
            "account": str(row["account"]),
        },
    }


def tool_recent_credit_card_transactions(csv_path: Path, limit: int = 5) -> dict:
    analytics = load_analytics(csv_path)
    rows = analytics.df[analytics.df["account"] == "credit_card"].copy()
    rows = rows.sort_values("date_parsed", ascending=False).head(limit)
    items = [
        {
            "date": str(row["date"]),
            "merchant": str(row["merchant"]),
            "amount": float(row["amount"]),
            "category": str(row["category"]),
        }
        for _, row in rows.iterrows()
    ]
    return {
        "tool": "recent_credit_card_transactions",
        "limit": int(limit),
        "items": items,
    }


def tool_compare_category_between_periods(
    csv_path: Path,
    category: str,
    left_period: str = "current_month",
    right_period: str = "last_week",
) -> dict:
    analytics = load_analytics(csv_path)
    left_start, left_end = _window_for_period(analytics.anchor_date, left_period)
    right_start, right_end = _window_for_period(analytics.anchor_date, right_period)
    left_total = spend_by_category(analytics, category=category, start=left_start, end=left_end)
    right_total = spend_by_category(analytics, category=category, start=right_start, end=right_end)
    delta = round(left_total - right_total, 2)
    return {
        "tool": "compare_category_between_periods",
        "category": category,
        "left": {
            "period": left_period,
            "start": left_start.date().isoformat(),
            "end": left_end.date().isoformat(),
            "total": round(left_total, 2),
        },
        "right": {
            "period": right_period,
            "start": right_start.date().isoformat(),
            "end": right_end.date().isoformat(),
            "total": round(right_total, 2),
        },
        "delta": delta,
    }


def tool_project_month_end_balance(csv_path: Path) -> dict:
    analytics = load_analytics(csv_path)
    anchor = analytics.anchor_date
    start, end = current_month_window(anchor)

    mask = (analytics.df["date_parsed"].dt.normalize() >= start.normalize()) & (
        analytics.df["date_parsed"].dt.normalize() <= end.normalize()
    )
    month_df = analytics.df.loc[mask]

    income = float(month_df.loc[month_df["amount"] > 0, "amount"].sum())
    spending = float((-month_df.loc[month_df["amount"] < 0, "amount"]).sum())

    days_elapsed = max(1, int(anchor.day))
    days_in_month = monthrange(anchor.year, anchor.month)[1]
    projected_spending = (spending / days_elapsed) * days_in_month
    projected_balance = income - projected_spending

    return {
        "tool": "project_month_end_balance",
        "month": anchor.strftime("%Y-%m"),
        "income": round(income, 2),
        "spending_to_date": round(spending, 2),
        "projected_spending": round(projected_spending, 2),
        "projected_balance": round(projected_balance, 2),
    }
