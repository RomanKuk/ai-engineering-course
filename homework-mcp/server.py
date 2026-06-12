from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from notes_store import NotesStore

mcp = FastMCP("notes")
store = NotesStore()


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_note(note: dict) -> str:
    tags = ", ".join(note["tags"]) if note["tags"] else "none"
    return (
        f"ID: {note['id']}\n"
        f"Title: {note['title']}\n"
        f"Tags: {tags}\n"
        f"Created: {note['created_at']}\n"
        f"Updated: {note['updated_at']}\n\n"
        f"{note['content']}"
    )


def _fmt_note_list(notes: list[dict]) -> str:
    if not notes:
        return "No notes found."
    lines = []
    for n in notes:
        tags = ", ".join(n["tags"]) if n["tags"] else "none"
        lines.append(f"• [{n['id']}] {n['title']}  (tags: {tags})  updated: {n['updated_at']}")
    return "\n".join(lines)


# ── tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def create_note(title: str, content: str, tags: list[str] = []) -> str:
    """Create a new note with a title and content. Optionally assign tags."""
    note = store.add(title=title, content=content, tags=tags)
    return f"Note created.\n\n{_fmt_note(note)}"


@mcp.tool()
def search_notes(query: str, limit: int = 10, tag: str | None = None) -> str:
    """Search notes by keyword. Optionally filter by tag and limit the number of results."""
    results = store.search(query=query, tag=tag, limit=limit)
    header = f"Found {len(results)} note(s) matching '{query}'"
    if tag:
        header += f" with tag '{tag}'"
    header += "."
    return f"{header}\n\n{_fmt_note_list(results)}"


@mcp.tool()
def delete_note(note_id: str) -> str:
    """Delete a note by its ID."""
    deleted = store.delete(note_id)
    if deleted:
        return f"Note {note_id} deleted successfully."
    return f"Note {note_id} not found."


@mcp.tool()
def update_note(
    note_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update a note's title, content, or tags. Only provided fields are changed."""
    note = store.update(note_id=note_id, title=title, content=content, tags=tags)
    if note is None:
        return f"Note {note_id} not found."
    return f"Note updated.\n\n{_fmt_note(note)}"


# ── resources ─────────────────────────────────────────────────────────────────

@mcp.resource("notes://all")
def list_notes_resource() -> str:
    """All notes as a structured list."""
    notes = store.list_all()
    if not notes:
        return "No notes yet. Use the create_note tool to add your first note."
    return json.dumps(notes, indent=2, ensure_ascii=False)


@mcp.resource("notes://{note_id}")
def get_note_resource(note_id: str) -> str:
    """A single note by ID."""
    note = store.get(note_id)
    if note is None:
        return f"Note '{note_id}' not found."
    return json.dumps(note, indent=2, ensure_ascii=False)


# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
