from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


_DEFAULT_PATH = Path(__file__).parent / "data" / "notes.json"


class NotesStore:
    """JSON-file-backed persistent store for notes."""

    def __init__(self, path: Path | None = None) -> None:
        env_path = os.environ.get("NOTES_DB_PATH")
        self._path = Path(env_path) if env_path else (path or _DEFAULT_PATH)
        self._notes: dict[str, dict] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._notes = {}
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._notes = {n["id"]: n for n in data if isinstance(n, dict) and "id" in n}
        except (json.JSONDecodeError, Exception):
            self._notes = {}

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(list(self._notes.values()), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _short_id() -> str:
        return "n_" + uuid.uuid4().hex[:6]

    # ── public API ────────────────────────────────────────────────────────────

    def add(self, title: str, content: str, tags: list[str] | None = None) -> dict:
        """Create a new note and return it."""
        note: dict = {
            "id": self._short_id(),
            "title": title.strip(),
            "content": content.strip(),
            "tags": [t.strip().lower() for t in (tags or [])],
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._notes[note["id"]] = note
        self._save()
        return note

    def get(self, note_id: str) -> dict | None:
        """Return a note by id, or None if not found."""
        return self._notes.get(note_id)

    def list_all(self) -> list[dict]:
        """Return all notes sorted by updated_at descending."""
        return sorted(self._notes.values(), key=lambda n: n["updated_at"], reverse=True)

    def search(
        self,
        query: str,
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Case-insensitive substring search over title + content with optional tag filter."""
        q = query.lower()
        results = []
        for note in self.list_all():
            if tag and tag.lower() not in note["tags"]:
                continue
            if q in note["title"].lower() or q in note["content"].lower():
                results.append(note)
            if len(results) >= limit:
                break
        return results

    def delete(self, note_id: str) -> bool:
        """Delete a note by id. Returns True if deleted, False if not found."""
        if note_id not in self._notes:
            return False
        del self._notes[note_id]
        self._save()
        return True

    def update(
        self,
        note_id: str,
        title: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> dict | None:
        """Update fields of an existing note. Returns updated note or None if not found."""
        note = self._notes.get(note_id)
        if note is None:
            return None
        if title is not None:
            note["title"] = title.strip()
        if content is not None:
            note["content"] = content.strip()
        if tags is not None:
            note["tags"] = [t.strip().lower() for t in tags]
        note["updated_at"] = self._now()
        self._save()
        return note
