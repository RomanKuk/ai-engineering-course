from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
from tqdm import tqdm


DEFAULT_CORPUS_PATH = Path("data/corpus.jsonl")
DEFAULT_QUERIES_PATH = Path("data/queries.jsonl")
DEFAULT_OUT_DIR = Path("data")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and cache document/query embeddings.")
    parser.add_argument("--model", required=True, help="Embedding model name. Example: BAAI/bge-small-en-v1.5 or text-embedding-3-small")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH, help="Path to corpus.jsonl")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_PATH, help="Path to queries.jsonl")
    parser.add_argument("--out_dir", type=Path, default=DEFAULT_OUT_DIR, help="Directory for .npy and .json outputs")
    parser.add_argument("--batch_size", type=int, default=128, help="Batch size for embedding requests")
    parser.add_argument("--max_docs", type=int, default=None, help="Optional limit for documents during smoke tests")
    parser.add_argument("--max_queries", type=int, default=None, help="Optional limit for queries during smoke tests")
    parser.add_argument("--force", action="store_true", help="Overwrite existing cached outputs")
    return parser.parse_args()


def model_slug(model_name: str) -> str:
    return model_name.replace("/", "_").replace("-", "_")


def read_jsonl_records(path: Path, limit: int | None = None) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    texts: list[str] = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if limit is not None and len(ids) >= limit:
                break
            record = json.loads(line)
            record_id = str(record["id"])
            text = str(record["text"]).strip()
            if not text:
                continue
            ids.append(record_id)
            texts.append(text)

    return ids, texts


def batched(items: list[str], batch_size: int) -> Iterator[list[str]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def normalize_rows(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-12, None)
    return (vectors / norms).astype(np.float32)


def embed_openai_batches(texts: list[str], model: str, batch_size: int) -> np.ndarray:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("openai is not installed. Run 'pip install openai' or add it to requirements.txt.") from exc

    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("OPENAI_API_KEY is not set. Set it in your shell before running embed.py.")

    client = OpenAI()
    all_vectors: list[np.ndarray] = []
    total_batches = (len(texts) + batch_size - 1) // batch_size
    progress = tqdm(batched(texts, batch_size), total=total_batches, desc=f"Embedding with {model}")

    for batch in progress:
        response = client.embeddings.create(model=model, input=batch)
        batch_vectors = np.array([item.embedding for item in response.data], dtype=np.float32)
        all_vectors.append(batch_vectors)

    return normalize_rows(np.vstack(all_vectors))


def embed_sentence_transformer_batches(texts: list[str], model: str, batch_size: int) -> np.ndarray:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ImportError(
            "sentence-transformers is not installed. Run 'pip install sentence-transformers'."
        ) from exc

    encoder = SentenceTransformer(model)
    vectors = encoder.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_texts(texts: list[str], model: str, batch_size: int) -> np.ndarray:
    if model.startswith("text-embedding-"):
        return embed_openai_batches(texts, model=model, batch_size=batch_size)
    return embed_sentence_transformer_batches(texts, model=model, batch_size=batch_size)


def write_ids(path: Path, ids: Iterable[str]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(list(ids), file, ensure_ascii=False)


def ensure_parent_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def output_paths(out_dir: Path, model: str) -> dict[str, Path]:
    slug = model_slug(model)
    return {
        "doc_embeddings": out_dir / f"doc_embeddings_{slug}.npy",
        "query_embeddings": out_dir / f"query_embeddings_{slug}.npy",
        "doc_ids": out_dir / f"doc_ids_{slug}.json",
        "query_ids": out_dir / f"query_ids_{slug}.json",
    }


def ensure_outputs_absent(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Re-run with --force to overwrite them.")


def main() -> None:
    args = parse_args()
    ensure_parent_dir(args.out_dir)

    paths = output_paths(args.out_dir, args.model)
    ensure_outputs_absent(paths, force=args.force)

    doc_ids, doc_texts = read_jsonl_records(args.corpus, limit=args.max_docs)
    query_ids, query_texts = read_jsonl_records(args.queries, limit=args.max_queries)

    if not doc_texts:
        raise ValueError(f"No documents were loaded from {args.corpus}.")
    if not query_texts:
        raise ValueError(f"No queries were loaded from {args.queries}.")

    print(f"Loaded {len(doc_ids)} documents from {args.corpus}")
    print(f"Loaded {len(query_ids)} queries from {args.queries}")

    doc_vectors = embed_texts(doc_texts, model=args.model, batch_size=args.batch_size)
    query_vectors = embed_texts(query_texts, model=args.model, batch_size=args.batch_size)

    np.save(paths["doc_embeddings"], doc_vectors)
    np.save(paths["query_embeddings"], query_vectors)
    write_ids(paths["doc_ids"], doc_ids)
    write_ids(paths["query_ids"], query_ids)

    print(f"Saved document embeddings: {doc_vectors.shape} -> {paths['doc_embeddings']}")
    print(f"Saved query embeddings: {query_vectors.shape} -> {paths['query_embeddings']}")
    print(f"Saved document IDs -> {paths['doc_ids']}")
    print(f"Saved query IDs -> {paths['query_ids']}")


if __name__ == "__main__":
    main()