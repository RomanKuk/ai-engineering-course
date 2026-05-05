from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple

import numpy as np


class VectorDB(ABC):
	"""Common interface for vector database benchmark backends."""

	@abstractmethod
	def index(self, vectors: np.ndarray, ids: List[str]) -> None:
		"""Build an index from vectors and their parallel string IDs."""

	@abstractmethod
	def search(self, query_vec: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
		"""Return the top-k nearest IDs and scores for a single query vector."""

	@abstractmethod
	def disk_size_mb(self) -> float:
		"""Return on-disk size in MB, or 0 for in-memory indexes."""

	def cleanup(self) -> None:
		"""Release resources after a benchmark run."""
		return None
