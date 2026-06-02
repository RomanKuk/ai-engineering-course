from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.analytics import load_analytics, summary


def main() -> None:
    csv_path = ROOT / "starter" / "data" / "transactions.csv"
    out_dir = ROOT / "var"
    out_dir.mkdir(parents=True, exist_ok=True)

    analytics = load_analytics(csv_path)
    result = summary(analytics)

    out_json = out_dir / "baseline_summary.json"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved {out_json}")


if __name__ == "__main__":
    main()
