"""
Run once to chunk, embed, and upsert the source PDF into Qdrant chunks_collection.
Usage: python scripts/index.py
       python scripts/index.py --source data/other.pdf
"""
import argparse
import os
import sys
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

load_dotenv()

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
COLLECTION = "chunks_collection"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
VECTOR_DIM = 384
DEFAULT_SOURCE = Path(__file__).parent.parent / "data" / "test.pdf"


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


def chunk_text(text: str) -> list[str]:
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks, start = [], 0
    while start < len(tokens):
        end = start + CHUNK_SIZE
        chunks.append(enc.decode(tokens[start:end]))
        if end >= len(tokens):
            break
        start = end - CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()

    if not args.source.exists():
        sys.exit(f"Source not found: {args.source}")

    print(f"Reading {args.source} ...")
    text = extract_text(args.source)
    chunks = chunk_text(text)
    print(f"Chunks: {len(chunks)}")

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(chunks, normalize_embeddings=True, show_progress_bar=True)

    client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))

    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION in existing:
        client.delete_collection(COLLECTION)

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )

    points = [
        PointStruct(
            id=i,
            vector=embeddings[i].tolist(),
            payload={"text": chunks[i], "chunk_id": f"chunk_{i}"},
        )
        for i in range(len(chunks))
    ]
    client.upsert(collection_name=COLLECTION, points=points)
    print(f"Indexed {len(points)} chunks into '{COLLECTION}'")


if __name__ == "__main__":
    main()
