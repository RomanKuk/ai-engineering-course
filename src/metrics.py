from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
	"""Recall@K = hits in top-k divided by min(k, number of relevant docs)."""
	if not relevant:
		return 0.0
	hits = len(set(retrieved[:k]) & relevant)
	return hits / min(k, len(relevant))


def mrr_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
	"""MRR@K = reciprocal rank of the first relevant result in top-k."""
	for rank, doc_id in enumerate(retrieved[:k], start=1):
		if doc_id in relevant:
			return 1.0 / rank
	return 0.0


def summarize_latencies(latency_runs_ms: Iterable[Sequence[float]]) -> dict[str, float]:
	"""Aggregate repeated latency runs by per-query median then percentile summary."""
	latency_array = np.asarray(list(latency_runs_ms), dtype=np.float64)
	if latency_array.size == 0:
		raise ValueError("Latency runs are empty.")
	per_query_median = np.median(latency_array, axis=0)
	return {
		"latency_p50_ms": round(float(np.percentile(per_query_median, 50)), 3),
		"latency_p95_ms": round(float(np.percentile(per_query_median, 95)), 3),
		"latency_p99_ms": round(float(np.percentile(per_query_median, 99)), 3),
	}
