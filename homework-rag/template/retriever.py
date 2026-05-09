from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from rank_bm25 import BM25Okapi


class Retriever(ABC):
    @abstractmethod
    def build(self, corpus: list[dict], embeddings: np.ndarray) -> None:
        """Index the corpus. embeddings[i] must correspond to corpus[i]."""

    @abstractmethod
    def search(self, query_vec: np.ndarray, top_k: int, query_text: str = "") -> list[str]:
        """Return top_k doc_ids ranked by relevance (best first)."""


class NumpyRetriever(Retriever):
    """Exact brute-force cosine similarity — O(N) per query."""

    def build(self, corpus: list[dict], embeddings: np.ndarray) -> None:
        self._ids = [doc["id"] for doc in corpus]
        self._vecs = embeddings  # (N, D), L2-normalized

    def search(self, query_vec: np.ndarray, top_k: int, query_text: str = "") -> list[str]:
        scores = self._vecs @ query_vec  # cosine via dot product on L2-normalized vecs
        k = min(top_k, len(self._ids))
        top_idx = np.argsort(scores)[::-1][:k]
        return [self._ids[i] for i in top_idx]


class FaissHNSWRetriever(Retriever):
    """Approximate nearest-neighbor via FAISS HNSW — sublinear query time."""

    def __init__(self, m: int = 32, ef_construction: int = 200, ef_search: int = 64):
        self._m = m
        self._ef_construction = ef_construction
        self._ef_search = ef_search

    def build(self, corpus: list[dict], embeddings: np.ndarray) -> None:
        import faiss

        dim = embeddings.shape[1]
        self._ids = [doc["id"] for doc in corpus]
        self._index = faiss.IndexHNSWFlat(dim, self._m, faiss.METRIC_INNER_PRODUCT)
        self._index.hnsw.efConstruction = self._ef_construction
        self._index.hnsw.efSearch = self._ef_search
        self._index.add(embeddings.astype(np.float32))

    def search(self, query_vec: np.ndarray, top_k: int, query_text: str = "") -> list[str]:
        q = query_vec.reshape(1, -1).astype(np.float32)
        _, indices = self._index.search(q, top_k)
        return [self._ids[i] for i in indices[0] if i >= 0]


class HybridRetriever(Retriever):
    """
    BM25 sparse + dense cosine fused with Reciprocal Rank Fusion (k=60).
    Fetches 2×top_k candidates from each component before fusion.
    Requires query_text to be passed at search time for BM25 scoring.
    """

    def __init__(self, rrf_k: int = 60):
        self._rrf_k = rrf_k
        self._dense = NumpyRetriever()

    def build(self, corpus: list[dict], embeddings: np.ndarray) -> None:
        self._ids = [doc["id"] for doc in corpus]
        self._dense.build(corpus, embeddings)
        tokenized = [doc["text"].lower().split() for doc in corpus]
        self._bm25 = BM25Okapi(tokenized)

    def search(self, query_vec: np.ndarray, top_k: int, query_text: str = "") -> list[str]:
        fetch_n = min(top_k * 2, len(self._ids))

        dense_ids = self._dense.search(query_vec, fetch_n)

        tokens = query_text.lower().split() if query_text else []
        if tokens:
            bm25_scores = self._bm25.get_scores(tokens)
            top_idx = np.argsort(bm25_scores)[::-1][:fetch_n]
            sparse_ids = [self._ids[i] for i in top_idx]
        else:
            sparse_ids = dense_ids  # fallback: no query text available

        rrf: dict[str, float] = {}
        for rank, doc_id in enumerate(dense_ids, start=1):
            rrf[doc_id] = rrf.get(doc_id, 0.0) + 1.0 / (self._rrf_k + rank)
        for rank, doc_id in enumerate(sparse_ids, start=1):
            rrf[doc_id] = rrf.get(doc_id, 0.0) + 1.0 / (self._rrf_k + rank)

        return sorted(rrf, key=rrf.__getitem__, reverse=True)[:top_k]
