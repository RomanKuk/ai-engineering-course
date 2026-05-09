"""
RAG scaling experiment: run three retrievers across four corpus sizes,
measure Recall@1, Recall@10, MRR@10, latency (p50/p95/p99), and RAM.

Usage:
    # Smoke test (streams only ~1500 docs, embeds 1K corpus + 10 queries):
    python experiment.py --max_size 1000 --max_queries 10

    # Full run (build corpus cache first if missing, then embed all sizes):
    python experiment.py
"""
import argparse
import csv
import gc
from pathlib import Path
from time import perf_counter

import numpy as np
import psutil

from data_loader import (
    build_corpus_pool,
    build_subset,
    load_cache,
    load_qrels_and_queries,
    pick_eval_queries,
    save_cache,
)
from embed import CACHE_DIR, embed_texts
from metrics import evaluate
from retriever import FaissHNSWRetriever, HybridRetriever, NumpyRetriever

CORPUS_SIZES = [1_000, 10_000, 100_000, 300_000]
N_EVAL = 200
TOP_K = 10
WARMUP_N = 5

RETRIEVER_FACTORIES = {
    "numpy": NumpyRetriever,
    "faiss_hnsw": FaissHNSWRetriever,
    "hybrid": HybridRetriever,
}


def _run_retriever(
    retriever,
    corpus: list[dict],
    corpus_vecs: np.ndarray,
    eval_set: list[dict],
    query_vecs: np.ndarray,
    query_texts: list[str],
) -> tuple[dict, list[float]]:
    retriever.build(corpus, corpus_vecs)

    for i in range(min(WARMUP_N, len(query_vecs))):
        retriever.search(query_vecs[i], TOP_K, query_texts[i])

    retrieved_per_query: list[list[str]] = []
    latencies_ms: list[float] = []
    for vec, text in zip(query_vecs, query_texts):
        t0 = perf_counter()
        ids = retriever.search(vec, TOP_K, text)
        latencies_ms.append((perf_counter() - t0) * 1000)
        retrieved_per_query.append(ids)

    metrics = evaluate(eval_set, retrieved_per_query, ks=(1, 10))
    return metrics, latencies_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG scaling experiment")
    parser.add_argument("--max_size", type=int, default=300_000, help="Largest corpus size to run")
    parser.add_argument("--max_queries", type=int, default=N_EVAL, help="Number of eval queries")
    parser.add_argument("--output", default="results.csv", help="Output CSV path")
    parser.add_argument(
        "--retrievers",
        nargs="+",
        default=list(RETRIEVER_FACTORIES.keys()),
        choices=list(RETRIEVER_FACTORIES.keys()),
        help="Retrievers to benchmark",
    )
    args = parser.parse_args()

    sizes = [s for s in CORPUS_SIZES if s <= args.max_size]

    # Distractor target scales with max_size so smoke tests don't stream the full corpus.
    # Cache is keyed by distractor_target so smoke and full runs don't share a stale cache.
    distractor_target = args.max_size + 500
    cache_path = Path(__file__).parent / "cache" / f"corpus_{distractor_target}.json"

    # ── Load or build corpus cache ────────────────────────────────────────────
    if cache_path.exists():
        print(f"Loading corpus from cache: {cache_path.name}")
        pool, full_eval_set = load_cache(cache_path)
    else:
        print(f"Streaming MS MARCO (need ~{distractor_target:,} docs, cached after)...")
        qrels, queries = load_qrels_and_queries()
        full_eval_set, relevant_ids = pick_eval_queries(qrels, queries, args.max_queries)
        pool = build_corpus_pool(relevant_ids, distractor_target)
        save_cache(pool, full_eval_set, cache_path)
        print(f"Corpus cached: {len(pool):,} docs, {len(full_eval_set)} eval queries")

    eval_set = full_eval_set[: args.max_queries]
    query_texts = [e["query"] for e in eval_set]

    # ── Embed queries once (keyed by count to avoid stale cache across runs) ──
    print(f"\nEmbedding {len(eval_set)} eval queries...")
    query_vecs = embed_texts(query_texts, cache_key=f"queries_{len(eval_set)}")

    rows: list[dict] = []

    for size in sizes:
        print(f"\n{'=' * 55}")
        print(f"Corpus size: {size:,}")

        corpus = build_subset(pool, eval_set, size)
        corpus_texts = [doc["text"] for doc in corpus]

        # Track whether embeddings come from cache to report meaningful throughput
        emb_cache = CACHE_DIR / f"embeddings_corpus_{size}.npy"
        from_cache = emb_cache.exists()
        t_embed = perf_counter()
        corpus_vecs = embed_texts(corpus_texts, cache_key=f"corpus_{size}")
        embed_time = perf_counter() - t_embed
        throughput = round(size / embed_time, 1) if not from_cache and embed_time > 0 else 0

        for rname in args.retrievers:
            print(f"  [{rname}] indexing + benchmarking {len(eval_set)} queries...")
            retriever = RETRIEVER_FACTORIES[rname]()

            metrics, latencies = _run_retriever(
                retriever, corpus, corpus_vecs, eval_set, query_vecs, query_texts
            )
            ram_mb = psutil.Process().memory_info().rss / 1e6

            lats = sorted(latencies)
            n = len(lats)
            row = {
                "size": size,
                "retriever": rname,
                "recall@1": metrics["recall@1"],
                "recall@10": metrics["recall@10"],
                "mrr@10": metrics["mrr@10"],
                "p50_ms": round(lats[min(int(n * 0.50), n - 1)], 3),
                "p95_ms": round(lats[min(int(n * 0.95), n - 1)], 3),
                "p99_ms": round(lats[min(int(n * 0.99), n - 1)], 3),
                "ram_mb": round(ram_mb, 1),
                "embed_throughput": throughput,
            }
            rows.append(row)
            print(
                f"  [{rname}] recall@1={row['recall@1']}  recall@10={row['recall@10']}  "
                f"mrr@10={row['mrr@10']}  |  p50={row['p50_ms']}ms  p95={row['p95_ms']}ms"
            )

            del retriever
            gc.collect()

    # ── Save results ──────────────────────────────────────────────────────────
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
