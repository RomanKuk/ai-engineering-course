from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

try:
    load_dotenv()
except UnicodeDecodeError:
    load_dotenv(encoding="utf-16")

CACHE_DIR = Path(__file__).parent / "cache"
MODEL = "text-embedding-3-small"
BATCH_SIZE = 2048


def _normalize(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (vecs / norms).astype(np.float32)


def embed_texts(
    texts: list[str],
    model: str = MODEL,
    batch_size: int = BATCH_SIZE,
    cache_key: str | None = None,
) -> np.ndarray:
    """
    Embed texts via OpenAI API. Returns L2-normalized float32 array of shape (N, 1536).
    Pass cache_key to save/load embeddings from cache/embeddings_{cache_key}.npy.
    """
    if cache_key:
        emb_path = CACHE_DIR / f"embeddings_{cache_key}.npy"
        if emb_path.exists():
            print(f"[embed] Cache hit: {emb_path.name}")
            return np.load(emb_path)

    client = OpenAI()
    all_vecs: list[list[float]] = []

    for i in tqdm(range(0, len(texts), batch_size), desc=f"Embedding via {model}"):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(input=batch, model=model)
        batch_vecs = [r.embedding for r in sorted(resp.data, key=lambda x: x.index)]
        all_vecs.extend(batch_vecs)

    embeddings = _normalize(np.array(all_vecs, dtype=np.float32))

    if cache_key:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(emb_path, embeddings)
        print(f"[embed] Saved to cache: {emb_path.name}")

    return embeddings
