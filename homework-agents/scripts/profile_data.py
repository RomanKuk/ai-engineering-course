from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = [
    "date",
    "merchant",
    "amount",
    "currency",
    "category",
    "account",
    "recurring",
]

ALLOWED_CATEGORIES = {
    "coffee",
    "groceries",
    "restaurants",
    "delivery",
    "transport",
    "entertainment",
    "shopping",
    "health",
    "subscriptions",
    "utilities",
    "salary",
    "credit_payment",
    "travel",
}

ALLOWED_ACCOUNTS = {"main_debit", "credit_card"}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "starter" / "data" / "transactions.csv"
    out_dir = root / "var"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df["date_parsed"] = pd.to_datetime(df["date"], errors="raise")

    if not (df["currency"] == "USD").all():
        raise ValueError("Currency contains non-USD values")

    bad_accounts = sorted(set(df["account"]) - ALLOWED_ACCOUNTS)
    if bad_accounts:
        raise ValueError(f"Unknown accounts: {bad_accounts}")

    bad_categories = sorted(set(df["category"]) - ALLOWED_CATEGORIES)
    if bad_categories:
        raise ValueError(f"Unknown categories: {bad_categories}")

    recurring_str = df["recurring"].astype(str).str.lower()
    if not recurring_str.isin({"true", "false"}).all():
        raise ValueError("Recurring has invalid values")

    profile = {
        "rows": int(len(df)),
        "min_date": df["date_parsed"].min().isoformat(),
        "max_date": df["date_parsed"].max().isoformat(),
        "unique_categories": sorted(df["category"].unique().tolist()),
        "unique_accounts": sorted(df["account"].unique().tolist()),
        "null_counts": df.isnull().sum().to_dict(),
        "negative_amount_count": int((df["amount"] < 0).sum()),
        "positive_amount_count": int((df["amount"] > 0).sum()),
    }

    out_path = out_dir / "profile.json"
    out_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(json.dumps(profile, indent=2))
    print(f"Saved profile to {out_path}")


if __name__ == "__main__":
    main()
