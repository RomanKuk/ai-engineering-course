from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class Analytics:
    df: pd.DataFrame
    anchor_date: pd.Timestamp


def load_analytics(csv_path: Path) -> Analytics:
    df = pd.read_csv(csv_path)
    df["date_parsed"] = pd.to_datetime(df["date"], errors="raise")
    anchor = df["date_parsed"].max().normalize()
    return Analytics(df=df, anchor_date=anchor)


def current_month_window(anchor_date: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = anchor_date.replace(day=1)
    end = anchor_date
    return start, end


def last_week_window(anchor_date: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    current_week_start = anchor_date - pd.Timedelta(days=anchor_date.weekday())
    start = current_week_start - pd.Timedelta(days=7)
    end = current_week_start - pd.Timedelta(days=1)
    return start, end


def spend_by_category(a: Analytics, category: str, start: pd.Timestamp, end: pd.Timestamp) -> float:
    mask = (
        (a.df["date_parsed"].dt.normalize() >= start.normalize())
        & (a.df["date_parsed"].dt.normalize() <= end.normalize())
        & (a.df["category"] == category)
        & (a.df["amount"] < 0)
    )
    return float((-a.df.loc[mask, "amount"]).sum())


def top_categories(a: Analytics, start: pd.Timestamp, end: pd.Timestamp, k: int = 5) -> list[dict]:
    mask = (
        (a.df["date_parsed"].dt.normalize() >= start.normalize())
        & (a.df["date_parsed"].dt.normalize() <= end.normalize())
        & (a.df["amount"] < 0)
        & (a.df["category"] != "credit_payment")
    )
    grouped = (-a.df.loc[mask].groupby("category")["amount"].sum()).sort_values(ascending=False).head(k)
    return [{"category": idx, "total": float(val)} for idx, val in grouped.items()]


def suspicious_credit_transactions(a: Analytics) -> list[dict]:
    suspicious_merchants = {"Booking.com", "AliExpress"}
    mask = (a.df["account"] == "credit_card") & (a.df["merchant"].isin(suspicious_merchants))
    rows = a.df.loc[mask, ["date", "merchant", "amount", "category"]].sort_values("date")
    return rows.to_dict(orient="records")


def late_night_delivery_share(a: Analytics) -> float:
    mask = (a.df["category"] == "delivery") & (a.df["amount"] < 0)
    data = a.df.loc[mask].copy()
    if data.empty:
        return 0.0
    data["hour"] = data["date_parsed"].dt.hour
    return float((data["hour"] >= 21).mean())


def weekend_spike_ratio(a: Analytics) -> float:
    data = a.df[a.df["amount"] < 0].copy()
    data["weekday"] = data["date_parsed"].dt.weekday
    weekday_avg = float((-data[data["weekday"] < 5]["amount"]).mean())
    weekend_avg = float((-data[data["weekday"] >= 5]["amount"]).mean())
    if weekday_avg == 0:
        return 0.0
    return weekend_avg / weekday_avg


def summary(a: Analytics) -> dict:
    cm_start, cm_end = current_month_window(a.anchor_date)
    lw_start, lw_end = last_week_window(a.anchor_date)
    return {
        "anchor_date": a.anchor_date.date().isoformat(),
        "coffee_last_week": spend_by_category(a, "coffee", lw_start, lw_end),
        "coffee_current_month": spend_by_category(a, "coffee", cm_start, cm_end),
        "top5_current_month": top_categories(a, cm_start, cm_end, 5),
        "late_night_delivery_share": late_night_delivery_share(a),
        "weekend_spike_ratio": weekend_spike_ratio(a),
        "suspicious_credit_transactions": suspicious_credit_transactions(a),
    }
