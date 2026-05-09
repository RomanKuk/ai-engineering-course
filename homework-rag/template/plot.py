"""
Visualize results from experiment.py.

Usage:
    python plot.py --input results.csv --output plots/
"""
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

COLORS = {
    "numpy": "#e74c3c",
    "faiss_hnsw": "#2ecc71",
    "hybrid": "#3498db",
}
LABELS = {
    "numpy": "Numpy (brute-force)",
    "faiss_hnsw": "FAISS HNSW",
    "hybrid": "Hybrid BM25+Dense+RRF",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="results.csv")
    parser.add_argument("--output", default="plots/")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    retrievers = df["retriever"].unique()

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("RAG Scaling Experiment — MS MARCO", fontsize=14, fontweight="bold")

    # 1. Recall@1 and Recall@10
    ax = axes[0, 0]
    for rname in retrievers:
        sub = df[df["retriever"] == rname]
        color = COLORS.get(rname, "gray")
        label = LABELS.get(rname, rname)
        ax.plot(sub["size"], sub["recall@1"], "o--", color=color, label=f"{label} @1", alpha=0.6)
        ax.plot(sub["size"], sub["recall@10"], "o-", color=color, label=f"{label} @10")
    ax.set_xscale("log")
    ax.set_xlabel("Corpus size")
    ax.set_ylabel("Recall")
    ax.set_title("Recall@1 and Recall@10 vs Corpus Size")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # 2. MRR@10
    ax = axes[0, 1]
    for rname in retrievers:
        sub = df[df["retriever"] == rname]
        color = COLORS.get(rname, "gray")
        label = LABELS.get(rname, rname)
        ax.plot(sub["size"], sub["mrr@10"], "o-", color=color, label=label)
    ax.set_xscale("log")
    ax.set_xlabel("Corpus size")
    ax.set_ylabel("MRR@10")
    ax.set_title("MRR@10 vs Corpus Size")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 3. Latency p50 / p95
    ax = axes[1, 0]
    for rname in retrievers:
        sub = df[df["retriever"] == rname]
        color = COLORS.get(rname, "gray")
        label = LABELS.get(rname, rname)
        ax.plot(sub["size"], sub["p50_ms"], "o--", color=color, label=f"{label} p50", alpha=0.6)
        ax.plot(sub["size"], sub["p95_ms"], "o-", color=color, label=f"{label} p95")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Corpus size")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Query Latency vs Corpus Size")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # 4. RAM
    ax = axes[1, 1]
    for rname in retrievers:
        sub = df[df["retriever"] == rname]
        color = COLORS.get(rname, "gray")
        label = LABELS.get(rname, rname)
        ax.plot(sub["size"], sub["ram_mb"], "o-", color=color, label=label)
    ax.set_xscale("log")
    ax.set_xlabel("Corpus size")
    ax.set_ylabel("RAM (MB)")
    ax.set_title("Memory Usage vs Corpus Size")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = out_dir / "scaling.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Plot saved to {out_path}")
    plt.show()

    print("\n--- Results Summary ---")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
