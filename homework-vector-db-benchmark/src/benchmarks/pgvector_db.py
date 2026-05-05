from __future__ import annotations

from typing import List, Tuple
from uuid import uuid4

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql

from benchmarks.base import VectorDB


class PgVectorDB(VectorDB):
	"""Postgres + pgvector HNSW backend using cosine distance."""

	def __init__(
		self,
		host: str = "localhost",
		port: int = 5432,
		user: str = "bench",
		password: str = "bench",
		database: str = "bench",
		collection: str | None = None,
		m: int = 16,
		ef_construction: int = 200,
		ef_search: int = 64,
		**_: object,
	) -> None:
		self.conn = psycopg.connect(
			host=host,
			port=port,
			user=user,
			password=password,
			dbname=database,
			autocommit=True,
		)
		self.table_name = collection or f"bench_{uuid4().hex}"
		self.index_name = f"{self.table_name}_hnsw_idx"
		self.m = m
		self.ef_construction = ef_construction
		self.ef_search = ef_search
		self._ensure_extension()
		register_vector(self.conn)

	def _ensure_extension(self) -> None:
		with self.conn.cursor() as cursor:
			cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")

	def index(self, vectors: np.ndarray, ids: List[str]) -> None:
		matrix = np.asarray(vectors, dtype=np.float32)
		if matrix.ndim != 2:
			raise ValueError(f"Expected a 2D vector matrix, got shape {matrix.shape}.")
		if len(ids) != len(matrix):
			raise ValueError("Vector count does not match ID count.")

		with self.conn.cursor() as cursor:
			cursor.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(self.table_name)))
			cursor.execute(
				sql.SQL("CREATE TABLE {} (doc_id TEXT PRIMARY KEY, embedding vector({}))").format(
					sql.Identifier(self.table_name),
					sql.SQL(str(matrix.shape[1])),
				)
			)

		insert_query = sql.SQL("INSERT INTO {} (doc_id, embedding) VALUES (%s, %s)").format(
			sql.Identifier(self.table_name)
		)
		batch_size = 1000
		for start in range(0, len(ids), batch_size):
			end = start + batch_size
			rows = [(str(doc_id), vector.tolist()) for doc_id, vector in zip(ids[start:end], matrix[start:end])]
			with self.conn.cursor() as cursor:
				cursor.executemany(insert_query, rows)

		with self.conn.cursor() as cursor:
			cursor.execute(sql.SQL("SET hnsw.ef_search = {}" ).format(sql.SQL(str(self.ef_search))))
			cursor.execute(
				sql.SQL(
					"CREATE INDEX {} ON {} USING hnsw (embedding vector_cosine_ops) WITH (m = {}, ef_construction = {})"
				).format(
					sql.Identifier(self.index_name),
					sql.Identifier(self.table_name),
					sql.SQL(str(self.m)),
					sql.SQL(str(self.ef_construction)),
				)
			)

	def search(self, query_vec: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
		query = np.asarray(query_vec, dtype=np.float32)
		if query.ndim != 1:
			query = query.reshape(-1)
		vector_literal = "[" + ",".join(str(float(value)) for value in query.tolist()) + "]"

		with self.conn.cursor() as cursor:
			cursor.execute(sql.SQL("SET hnsw.ef_search = {}" ).format(sql.SQL(str(self.ef_search))))
			cursor.execute(
				sql.SQL(
					"SELECT doc_id, 1 - (embedding <=> %s::vector) AS score FROM {} ORDER BY embedding <=> %s::vector LIMIT %s"
				).format(sql.Identifier(self.table_name)),
				(vector_literal, vector_literal, top_k),
			)
			rows = cursor.fetchall()
		return [(str(doc_id), float(score)) for doc_id, score in rows]

	def disk_size_mb(self) -> float:
		with self.conn.cursor() as cursor:
			cursor.execute(
				"SELECT COALESCE(pg_total_relation_size(%s::regclass), 0)",
				(self.table_name,),
			)
			size_bytes = cursor.fetchone()[0]
		return float(size_bytes) / (1024 * 1024)

	def cleanup(self) -> None:
		try:
			with self.conn.cursor() as cursor:
				cursor.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(self.table_name)))
		finally:
			self.conn.close()
