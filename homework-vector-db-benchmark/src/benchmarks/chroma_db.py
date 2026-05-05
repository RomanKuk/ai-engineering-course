from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Tuple
from uuid import uuid4

import chromadb
import numpy as np

from benchmarks.base import VectorDB


class ChromaDB(VectorDB):
	"""Persistent embedded Chroma benchmark backend."""

	def __init__(self, collection: str | None = None, persist_dir: str = "data/chroma_store", **_: object) -> None:
		self.persist_path = Path(persist_dir)
		self.persist_path.mkdir(parents=True, exist_ok=True)
		self.collection_name = collection or f"bench_{uuid4().hex}"
		self.client = chromadb.PersistentClient(path=str(self.persist_path))
		self.collection = None

	def index(self, vectors: np.ndarray, ids: List[str]) -> None:
		matrix = np.asarray(vectors, dtype=np.float32)
		if matrix.ndim != 2:
			raise ValueError(f"Expected a 2D vector matrix, got shape {matrix.shape}.")
		if len(ids) != len(matrix):
			raise ValueError("Vector count does not match ID count.")

		try:
			self.client.delete_collection(self.collection_name)
		except Exception:
			pass

		self.collection = self.client.get_or_create_collection(
			name=self.collection_name,
			metadata={"hnsw:space": "cosine"},
		)

		batch_size = 1000
		for start in range(0, len(ids), batch_size):
			end = start + batch_size
			self.collection.add(
				ids=[str(doc_id) for doc_id in ids[start:end]],
				embeddings=matrix[start:end].tolist(),
			)

	def search(self, query_vec: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
		if self.collection is None:
			raise RuntimeError("The Chroma collection has not been built yet.")

		query = np.asarray(query_vec, dtype=np.float32)
		if query.ndim != 1:
			query = query.reshape(-1)

		result = self.collection.query(query_embeddings=[query.tolist()], n_results=top_k)
		ids = result.get("ids", [[]])[0]
		distances = result.get("distances", [[]])[0]
		return [(str(doc_id), float(1.0 - distance)) for doc_id, distance in zip(ids, distances)]

	def disk_size_mb(self) -> float:
		total_bytes = 0
		if not self.persist_path.exists():
			return 0.0
		for child in self.persist_path.rglob("*"):
			if child.is_file():
				total_bytes += child.stat().st_size
		return total_bytes / (1024 * 1024)

	def cleanup(self) -> None:
		try:
			self.client.delete_collection(self.collection_name)
		except Exception:
			pass


