from __future__ import annotations

from typing import List, Tuple

import faiss
import numpy as np

from benchmarks.base import VectorDB


class FaissHNSWDB(VectorDB):
	"""Approximate nearest-neighbor search with FAISS HNSW."""

	def __init__(self, m: int = 32, ef_construction: int = 200, ef_search: int = 128, **_: object) -> None:
		self.m = m
		self.ef_construction = ef_construction
		self.ef_search = ef_search
		self.index_handle: faiss.IndexHNSWFlat | None = None
		self.doc_ids: list[str] = []

	def index(self, vectors: np.ndarray, ids: List[str]) -> None:
		matrix = np.asarray(vectors, dtype=np.float32)
		if matrix.ndim != 2:
			raise ValueError(f"Expected a 2D vector matrix, got shape {matrix.shape}.")
		if len(ids) != len(matrix):
			raise ValueError("Vector count does not match ID count.")

		index = faiss.IndexHNSWFlat(matrix.shape[1], self.m, faiss.METRIC_INNER_PRODUCT)
		index.hnsw.efConstruction = self.ef_construction
		index.hnsw.efSearch = self.ef_search
		index.add(np.ascontiguousarray(matrix))

		self.index_handle = index
		self.doc_ids = [str(doc_id) for doc_id in ids]

	def search(self, query_vec: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
		if self.index_handle is None:
			raise RuntimeError("The FAISS HNSW index has not been built yet.")

		query = np.asarray(query_vec, dtype=np.float32)
		if query.ndim == 1:
			query = query.reshape(1, -1)
		elif query.ndim != 2 or query.shape[0] != 1:
			raise ValueError(f"Expected query vector of shape (dim,) or (1, dim), got {query.shape}.")

		scores, indices = self.index_handle.search(np.ascontiguousarray(query), top_k)
		results: List[Tuple[str, float]] = []
		for raw_index, score in zip(indices[0], scores[0]):
			if raw_index < 0:
				continue
			results.append((self.doc_ids[int(raw_index)], float(score)))
		return results

	def disk_size_mb(self) -> float:
		return 0.0

	def cleanup(self) -> None:
		self.index_handle = None
		self.doc_ids = []
