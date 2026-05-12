from __future__ import annotations

import os
import time
import uuid
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

CACHE_COLLECTION = "cache_collection"
SIMILARITY_THRESHOLD = 0.92
TTL_SECONDS = 3600
VECTOR_DIM = 384

_qdrant: AsyncQdrantClient | None = None


def _get_qdrant() -> AsyncQdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = AsyncQdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
        )
    return _qdrant


async def init_cache_collection() -> None:
    client = _get_qdrant()
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]
    if CACHE_COLLECTION not in names:
        await client.create_collection(
            collection_name=CACHE_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )


async def cache_check(query_vec: list[float]) -> str | None:
    client = _get_qdrant()
    result = await client.query_points(
        collection_name=CACHE_COLLECTION,
        query=query_vec,
        limit=1,
        with_payload=True,
        score_threshold=SIMILARITY_THRESHOLD,
    )
    hits = result.points
    if not hits:
        return None
    payload = hits[0].payload or {}
    if payload.get("expire_at", 0) < time.time():
        return None
    return payload.get("response")


async def cache_store(query_vec: list[float], query: str, response: str, model: str) -> None:
    client = _get_qdrant()
    await client.upsert(
        collection_name=CACHE_COLLECTION,
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=query_vec,
                payload={
                    "query": query,
                    "response": response,
                    "model": model,
                    "expire_at": time.time() + TTL_SECONDS,
                    "created_at": time.time(),
                },
            )
        ],
    )
