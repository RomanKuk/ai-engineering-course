from __future__ import annotations

import argparse
import csv
import importlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


DEFAULT_DATA_DIR = Path("data")
DEFAULT_RESULTS_PATH = Path("results/results.csv")
DEFAULT_MODEL = "text-embedding-3-small"

DB_REGISTRY = {
	"faiss_flat": ("benchmarks.faiss_flat", "FaissFlatDB"),
	"faiss_hnsw": ("benchmarks.faiss_hnsw", "FaissHNSWDB"),
	"qdrant": ("benchmarks.qdrant_db", "QdrantDB"),
	"chroma": ("benchmarks.chroma_db", "ChromaDB"),
	"pgvector": ("benchmarks.pgvector_db", "PgVectorDB"),
}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Run vector database benchmarks on cached embeddings.")
	parser.add_argument("--db", choices=sorted(DB_REGISTRY), help="Database backend to benchmark. Omit to run all backends.")
	parser.add_argument("--model", default=DEFAULT_MODEL, help="Embedding model name used when generating cached vectors")
	parser.add_argument("--data_dir", type=Path, default=DEFAULT_DATA_DIR, help="Directory containing embeddings and qrels")
	parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS_PATH, help="CSV file to append benchmark results to")
	parser.add_argument("--top_k", type=int, default=10, help="Top-K results to request from each DB")
	parser.add_argument("--warmup_queries", type=int, default=50, help="Warmup queries excluded from timing")
	parser.add_argument("--num_repeats", type=int, default=3, help="Number of timed query passes")
	parser.add_argument("--max_docs", type=int, default=None, help="Optional document limit for smoke tests")
	parser.add_argument("--max_queries", type=int, default=None, help="Optional query limit for smoke tests")
	parser.add_argument("--host", default="localhost", help="Optional host for remote DB backends")
	parser.add_argument("--port", type=int, default=None, help="Optional port for remote DB backends")
	parser.add_argument("--user", default=None, help="Optional username for DB backends")
	parser.add_argument("--password", default=None, help="Optional password for DB backends")
	parser.add_argument("--database", default=None, help="Optional database name for DB backends")
	parser.add_argument("--collection", default=None, help="Optional collection/index name for DB backends")
	return parser.parse_args()


def selected_backends(args: argparse.Namespace) -> list[str]:
	if args.db:
		return [args.db]
	return list(DB_REGISTRY.keys())


def model_slug(model_name: str) -> str:
	return model_name.replace("/", "_").replace("-", "_")


def cached_paths(data_dir: Path, model_name: str) -> dict[str, Path]:
	slug = model_slug(model_name)
	return {
		"doc_embeddings": data_dir / f"doc_embeddings_{slug}.npy",
		"query_embeddings": data_dir / f"query_embeddings_{slug}.npy",
		"doc_ids": data_dir / f"doc_ids_{slug}.json",
		"query_ids": data_dir / f"query_ids_{slug}.json",
		"qrels": data_dir / "qrels.tsv",
	}


def ensure_files_exist(paths: dict[str, Path]) -> None:
	missing = [str(path) for path in paths.values() if not path.exists()]
	if missing:
		joined = ", ".join(missing)
		raise FileNotFoundError(f"Missing required input files: {joined}")


def load_json_list(path: Path) -> list[str]:
	with path.open("r", encoding="utf-8") as file:
		values = json.load(file)
	return [str(value) for value in values]


def load_qrels(path: Path) -> Dict[str, set[str]]:
	qrels: Dict[str, set[str]] = {}
	with path.open("r", encoding="utf-8", newline="") as file:
		reader = csv.DictReader(file, delimiter="\t")
		for row in reader:
			query_id = str(row["query_id"])
			doc_id = str(row["doc_id"])
			score = int(row["score"])
			if score <= 0:
				continue
			qrels.setdefault(query_id, set()).add(doc_id)
	return qrels


def maybe_limit_parallel(vectors: np.ndarray, ids: list[str], limit: int | None) -> tuple[np.ndarray, list[str]]:
	if limit is None:
		return vectors, ids
	return vectors[:limit], ids[:limit]


def filter_queries_with_qrels(
	query_vectors: np.ndarray, query_ids: list[str], qrels: Dict[str, set[str]]
) -> tuple[np.ndarray, list[str]]:
	keep_indices = [index for index, query_id in enumerate(query_ids) if query_id in qrels]
	if not keep_indices:
		raise ValueError("No query IDs overlap with qrels. Check that your exported IDs match the qrels file.")
	filtered_vectors = query_vectors[keep_indices]
	filtered_ids = [query_ids[index] for index in keep_indices]
	return filtered_vectors, filtered_ids


def _recall_at_k(retrieved: List[str], relevant: set[str], k: int) -> float:
	if not relevant:
		return 0.0
	hits = len(set(retrieved[:k]) & relevant)
	return hits / min(k, len(relevant))


def _mrr_at_k(retrieved: List[str], relevant: set[str], k: int) -> float:
	for rank, doc_id in enumerate(retrieved[:k], start=1):
		if doc_id in relevant:
			return 1.0 / rank
	return 0.0


def benchmark_db(
	db: Any,
	doc_vectors: np.ndarray,
	doc_ids: List[str],
	query_vectors: np.ndarray,
	query_ids: List[str],
	qrels: Dict[str, set[str]],
	top_k: int,
	warmup_queries: int,
	num_repeats: int,
) -> Dict[str, Any]:
	t0 = time.perf_counter()
	db.index(doc_vectors, ids=doc_ids)
	index_time = time.perf_counter() - t0

	warmup_count = min(warmup_queries, len(query_vectors))
	for query_vec in query_vectors[:warmup_count]:
		db.search(query_vec, top_k=top_k)

	all_latencies: List[List[float]] = []
	recalls: List[float] = []
	mrrs: List[float] = []

	for repeat in range(num_repeats):
		latencies: List[float] = []
		for query_vec, query_id in zip(query_vectors, query_ids):
			t0 = time.perf_counter()
			results = db.search(query_vec, top_k=top_k)
			latencies.append((time.perf_counter() - t0) * 1000.0)

			if repeat == 0:
				retrieved_ids = [doc_id for doc_id, _score in results]
				relevant = qrels.get(query_id, set())
				recalls.append(_recall_at_k(retrieved_ids, relevant, top_k))
				mrrs.append(_mrr_at_k(retrieved_ids, relevant, top_k))
		all_latencies.append(latencies)

	latencies_arr = np.median(np.asarray(all_latencies, dtype=np.float64), axis=0)
	disk_mb = float(db.disk_size_mb()) if hasattr(db, "disk_size_mb") else 0.0

	return {
		"index_time_sec": round(index_time, 2),
		"disk_mb": round(disk_mb, 1),
		"latency_p50_ms": round(float(np.percentile(latencies_arr, 50)), 3),
		"latency_p95_ms": round(float(np.percentile(latencies_arr, 95)), 3),
		"latency_p99_ms": round(float(np.percentile(latencies_arr, 99)), 3),
		"recall_at_10": round(float(np.mean(recalls)), 4),
		"mrr_at_10": round(float(np.mean(mrrs)), 4),
		"num_docs": len(doc_vectors),
		"num_queries": len(query_vectors),
		"top_k": top_k,
		"warmup_queries": warmup_count,
		"num_repeats": num_repeats,
	}


def backend_connection_defaults(backend_name: str) -> dict[str, Any]:
	defaults: dict[str, Any] = {}
	if backend_name == "qdrant":
		defaults["port"] = 6333
	elif backend_name == "pgvector":
		defaults["port"] = 5432
		defaults["user"] = "bench"
		defaults["password"] = "bench"
		defaults["database"] = "bench"
	return defaults


def instantiate_db(backend_name: str, args: argparse.Namespace) -> Any:
	module_name, class_name = DB_REGISTRY[backend_name]
	try:
		module = importlib.import_module(module_name)
	except ImportError as exc:
		raise ImportError(f"Could not import backend module '{module_name}'.") from exc

	if not hasattr(module, class_name):
		raise NotImplementedError(
			f"Backend '{backend_name}' is not implemented yet. Expected class '{class_name}' in module '{module_name}'."
		)

	backend_class = getattr(module, class_name)
	defaults = backend_connection_defaults(backend_name)
	init_kwargs = {
		"host": args.host,
		"port": args.port if args.port is not None else defaults.get("port"),
		"user": args.user if args.user is not None else defaults.get("user"),
		"password": args.password if args.password is not None else defaults.get("password"),
		"database": args.database if args.database is not None else defaults.get("database"),
		"collection": args.collection,
	}
	filtered_kwargs = {key: value for key, value in init_kwargs.items() if value is not None}
	return backend_class(**filtered_kwargs)


def append_result_row(path: Path, row: Dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	write_header = not path.exists()
	fieldnames = list(row.keys())
	with path.open("a", encoding="utf-8", newline="") as file:
		writer = csv.DictWriter(file, fieldnames=fieldnames)
		if write_header:
			writer.writeheader()
		writer.writerow(row)


def load_benchmark_inputs(args: argparse.Namespace) -> tuple[np.ndarray, list[str], np.ndarray, list[str], Dict[str, set[str]]]:
	paths = cached_paths(args.data_dir, args.model)
	ensure_files_exist(paths)

	doc_vectors = np.load(paths["doc_embeddings"])
	query_vectors = np.load(paths["query_embeddings"])
	doc_ids = load_json_list(paths["doc_ids"])
	query_ids = load_json_list(paths["query_ids"])
	qrels = load_qrels(paths["qrels"])

	if len(doc_vectors) != len(doc_ids):
		raise ValueError("Document embedding count does not match document ID count.")
	if len(query_vectors) != len(query_ids):
		raise ValueError("Query embedding count does not match query ID count.")

	doc_vectors, doc_ids = maybe_limit_parallel(doc_vectors, doc_ids, args.max_docs)
	query_vectors, query_ids = filter_queries_with_qrels(query_vectors, query_ids, qrels)
	query_vectors, query_ids = maybe_limit_parallel(query_vectors, query_ids, args.max_queries)
	return doc_vectors, doc_ids, query_vectors, query_ids, qrels


def progress_prefix(current: int, total: int) -> str:
	percentage = round((current / total) * 100)
	return f"[{current}/{total} | {percentage}%]"


def main() -> None:
	args = parse_args()
	backends = selected_backends(args)
	doc_vectors, doc_ids, query_vectors, query_ids, qrels = load_benchmark_inputs(args)

	print(f"Using model: {args.model}")
	print(f"Loaded {len(doc_ids)} documents and {len(query_ids)} queries.")
	print(f"Backends to run: {', '.join(backends)}")

	failures: list[tuple[str, str]] = []
	for index, backend_name in enumerate(backends, start=1):
		prefix = progress_prefix(index, len(backends))
		print(f"{prefix} Starting backend: {backend_name}")
		backend_defaults = backend_connection_defaults(backend_name)
		runtime_port = args.port if args.port is not None else backend_defaults.get("port")
		runtime_database = args.database if args.database is not None else backend_defaults.get("database")

		try:
			db = instantiate_db(backend_name, args)
			try:
				metrics = benchmark_db(
					db=db,
					doc_vectors=doc_vectors,
					doc_ids=doc_ids,
					query_vectors=query_vectors,
					query_ids=query_ids,
					qrels=qrels,
					top_k=args.top_k,
					warmup_queries=args.warmup_queries,
					num_repeats=args.num_repeats,
				)
			finally:
				if hasattr(db, "cleanup"):
					db.cleanup()

			result_row = {
				"db": backend_name,
				"model": args.model,
				"host": args.host,
				"port": runtime_port,
				"database": runtime_database,
				"collection": args.collection,
				**metrics,
			}
			append_result_row(args.output, result_row)
			print(f"{prefix} Finished backend: {backend_name}")
			print(
				f"{prefix} recall@10={result_row['recall_at_10']} p50={result_row['latency_p50_ms']}ms "
				f"index={result_row['index_time_sec']}s"
			)
		except Exception as exc:
			failures.append((backend_name, str(exc)))
			print(f"{prefix} Failed backend: {backend_name}")
			print(f"{prefix} Error: {exc}")

	print(f"Completed benchmark run. Results file: {args.output}")
	if failures:
		print("Failures:")
		for backend_name, message in failures:
			print(f"  {backend_name}: {message}")
		raise SystemExit(1)


if __name__ == "__main__":
	main()
