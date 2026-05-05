from __future__ import annotations

import csv
import json
import shutil
import ssl
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable, Iterator

import certifi
from datasets import load_dataset


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORPUS_PATH = DATA_DIR / "corpus.jsonl"
QUERIES_PATH = DATA_DIR / "queries.jsonl"
QRELS_PATH = DATA_DIR / "qrels.tsv"
BEIR_QUORA_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/quora.zip"


def ensure_data_dir() -> None:
	DATA_DIR.mkdir(parents=True, exist_ok=True)


def combine_text(title: str, text: str) -> str:
	title = (title or "").strip()
	text = (text or "").strip()
	if title and text:
		return f"{title}\n\n{text}"
	return title or text


def iter_corpus_rows() -> Iterator[dict[str, str]]:
	dataset = load_dataset("BeIR/quora", "corpus", split="corpus")
	for row in dataset:
		text = combine_text(row.get("title", ""), row.get("text", ""))
		if not text:
			continue
		yield {"id": str(row["_id"]), "text": text}


def iter_query_rows() -> Iterator[dict[str, str]]:
	dataset = load_dataset("BeIR/quora", "queries", split="queries")
	for row in dataset:
		text = combine_text(row.get("title", ""), row.get("text", ""))
		if not text:
			continue
		yield {"id": str(row["_id"]), "text": text}


def write_jsonl(path: Path, rows: Iterable[dict[str, str]]) -> int:
	count = 0
	with path.open("w", encoding="utf-8") as file:
		for row in rows:
			file.write(json.dumps(row, ensure_ascii=False) + "\n")
			count += 1
	return count


def download_file(url: str, destination: Path) -> None:
	ssl_context = ssl.create_default_context(cafile=certifi.where())
	with urllib.request.urlopen(url, context=ssl_context) as response, destination.open("wb") as file:
		shutil.copyfileobj(response, file)


def extract_qrels_source(destination: Path) -> Path:
	with tempfile.TemporaryDirectory() as temp_dir:
		zip_path = Path(temp_dir) / "quora.zip"
		download_file(BEIR_QUORA_URL, zip_path)

		with zipfile.ZipFile(zip_path) as archive:
			for member in archive.namelist():
				normalized = member.replace("\\", "/")
				if normalized.endswith("/qrels/test.tsv") or normalized.endswith("/qrels/dev.tsv"):
					split_name = Path(normalized).stem
					target_path = destination / f"{split_name}.tsv"
					with archive.open(member) as source, target_path.open("wb") as target:
						shutil.copyfileobj(source, target)

	test_path = destination / "test.tsv"
	if test_path.exists():
		return test_path

	dev_path = destination / "dev.tsv"
	if dev_path.exists():
		return dev_path

	raise FileNotFoundError("Could not find qrels/test.tsv or qrels/dev.tsv in the BEIR Quora archive.")


def write_qrels_tsv(path: Path) -> tuple[int, str]:
	with tempfile.TemporaryDirectory() as temp_dir:
		source_path = extract_qrels_source(Path(temp_dir))
		split_name = source_path.stem
		count = 0
		with source_path.open("r", encoding="utf-8") as source, path.open(
			"w", encoding="utf-8", newline=""
		) as destination:
			reader = csv.DictReader(source, delimiter="\t")
			writer = csv.writer(destination, delimiter="\t")
			writer.writerow(["query_id", "doc_id", "score"])
			for row in reader:
				writer.writerow([str(row["query-id"]), str(row["corpus-id"]), int(row["score"])])
				count += 1

	return count, split_name


def main() -> None:
	ensure_data_dir()

	num_docs = write_jsonl(CORPUS_PATH, iter_corpus_rows())
	num_queries = write_jsonl(QUERIES_PATH, iter_query_rows())
	num_qrels, qrels_split = write_qrels_tsv(QRELS_PATH)

	print(f"Saved corpus: {num_docs} docs -> {CORPUS_PATH}")
	print(f"Saved queries: {num_queries} queries -> {QUERIES_PATH}")
	print(f"Saved qrels: {num_qrels} rows from '{qrels_split}' split -> {QRELS_PATH}")
	print(f"Data directory: {DATA_DIR}")


if __name__ == "__main__":
	main()
