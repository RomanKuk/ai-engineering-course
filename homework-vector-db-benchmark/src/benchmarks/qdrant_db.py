from __future__ import annotations

from typing import List, Tuple
from uuid import uuid4

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models

from benchmarks.base import VectorDB


class QdrantDB(VectorDB):
	"""Remote Qdrant backend using cosine distance."""

	def __init__(
		self,
		host: str = "localhost",
		port: int = 6333,
		collection: str | None = None,
		m: int = 32,
		ef_construct: int = 200,
		full_scan_threshold: int = 10000,
		**_: object,
	) -> None:
		self.client = QdrantClient(host=host, port=port)
		self.collection_name = collection or f"bench_{uuid4().hex}"
		self.m = m
		self.ef_construct = ef_construct
		self.full_scan_threshold = full_scan_threshold
		self.id_map: dict[int, str] = {}

	def index(self, vectors: np.ndarray, ids: List[str]) -> None:
		matrix = np.asarray(vectors, dtype=np.float32)
		if matrix.ndim != 2:
			raise ValueError(f"Expected a 2D vector matrix, got shape {matrix.shape}.")
		if len(ids) != len(matrix):
			raise ValueError("Vector count does not match ID count.")

		self.client.recreate_collection(
			collection_name=self.collection_name,
			vectors_config=models.VectorParams(size=matrix.shape[1], distance=models.Distance.COSINE),
			hnsw_config=models.HnswConfigDiff(
				m=self.m,
				ef_construct=self.ef_construct,
				full_scan_threshold=self.full_scan_threshold,
			),
		)

		batch_size = 1000
		for start in range(0, len(ids), batch_size):
			end = start + batch_size
			points = [
				models.PointStruct(
					id=start + offset,
					vector=vector.tolist(),
					payload={"doc_id": str(doc_id)},
				)
				for offset, (doc_id, vector) in enumerate(zip(ids[start:end], matrix[start:end]))
			]
			for offset, doc_id in enumerate(ids[start:end]):
				self.id_map[start + offset] = str(doc_id)
			self.client.upsert(collection_name=self.collection_name, points=points, wait=True)

	def search(self, query_vec: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
		query = np.asarray(query_vec, dtype=np.float32)
		if query.ndim != 1:
			query = query.reshape(-1)

		result = self.client.query_points(
			collection_name=self.collection_name,
			query=query.tolist(),
			limit=top_k,
		)
		points = getattr(result, "points", result)
		results: List[Tuple[str, float]] = []
		for point in points:
			payload = getattr(point, "payload", None) or {}
			doc_id = payload.get("doc_id", self.id_map.get(int(point.id), str(point.id)))
			results.append((str(doc_id), float(point.score)))
		return results

	def disk_size_mb(self) -> float:
		return 0.0

	def cleanup(self) -> None:
		try:
			self.client.delete_collection(self.collection_name)
		except Exception:
			pass
		self.id_map = {}
