from __future__ import annotations

import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import AsyncQdrantClient

load_dotenv()

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
CHUNKS_COLLECTION = "chunks_collection"
VECTOR_DIM = 384

_hf_token = os.getenv("HF_TOKEN")
_model = SentenceTransformer(EMBEDDING_MODEL, token=_hf_token)
_qdrant: AsyncQdrantClient | None = None


def _get_qdrant() -> AsyncQdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = AsyncQdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
        )
    return _qdrant


def embed(text: str) -> list[float]:
    return _model.encode(text, normalize_embeddings=True).tolist()


async def retrieve(query_vec: list[float], top_k: int = 3) -> list[dict]:
    client = _get_qdrant()
    result = await client.query_points(
        collection_name=CHUNKS_COLLECTION,
        query=query_vec,
        limit=top_k,
        with_payload=True,
    )
    return [{"id": h.payload.get("chunk_id", str(h.id)), "text": h.payload.get("text", ""), "score": h.score} for h in result.points]
