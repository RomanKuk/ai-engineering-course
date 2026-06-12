# Homework MCP — Notes Server

A personal notes MCP server built with [FastMCP](https://github.com/modelcontextprotocol/python-sdk). Stores notes locally in a JSON file and exposes them to Claude Desktop via **stdio** transport.

## Setup

```bash
# From repo root
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

cd homework-mcp
pip install -r requirements.txt
```

By default notes are saved to `homework-mcp/data/notes.json`. Override with an env var:

```bash
export NOTES_DB_PATH=/your/custom/path/notes.json
```

---

## Connecting to Claude Desktop

**1. Find your config file:**

| Platform | Path |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

**2. Add the `notes` server entry.** Merge the snippet below into the `mcpServers` object (create the file if it doesn't exist):

```json
{
  "mcpServers": {
    "notes": {
      "command": "C:\\path\\to\\ai-engineering-course\\homework-mcp\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\path\\to\\ai-engineering-course\\homework-mcp\\server.py"
      ]
    }
  }
}
```

> **Tip:** Use the **venv Python** inside `homework-mcp/.venv/Scripts/python.exe` — **not** the system Python or another homework's venv. The `mcp` package requires Python 3.10+ and is installed in `homework-mcp/.venv`. Adjust backslashes / forward-slashes for your OS.

**3. Restart Claude Desktop** (quit fully and relaunch).

**4. Verify:** Open a new conversation — you should see a small hammer/tools icon indicating the `notes` server and its 4 tools are available.

---

## Tools

| Tool | Required args | Optional args | Description |
|---|---|---|---|
| `create_note` | `title`, `content` | `tags` (list of strings) | Create a new note |
| `search_notes` | `query` | `limit` (int, default 10), `tag` (string) | Full-text search over title + content |
| `delete_note` | `note_id` | — | Delete a note by ID |
| `update_note` | `note_id` | `title`, `content`, `tags` | Update any field of an existing note |

---

## Resources

| URI | Description |
|---|---|
| `notes://all` | JSON array of all notes, sorted newest-first |
| `notes://{note_id}` | Single note JSON by ID (e.g. `notes://n_ab12cd`) |

Resources are readable directly in Claude Desktop by referencing them in your prompt or via the MCP Inspector.

---

## Example Dialogs

### Dialog 1 — Create a note with tags

**User:** Create a note titled "Sprint planning" with the content "Review backlog, set capacity, assign stories" and tag it with "work" and "planning".

**Claude:** *(calls `create_note`)* Note created.

```
ID: n_3f7a1b
Title: Sprint planning
Tags: work, planning
Created: 2026-06-12T10:00:00+00:00
Updated: 2026-06-12T10:00:00+00:00

Review backlog, set capacity, assign stories
```

*(See `examples/01-create-note.png`)*

---

### Dialog 2 — Search for notes by keyword and tag

**User:** Find my notes about "backlog" tagged with "work".

**Claude:** *(calls `search_notes` with query="backlog", tag="work")* Found 1 note(s) matching 'backlog' with tag 'work'.

```
• [n_3f7a1b] Sprint planning  (tags: work, planning)  updated: 2026-06-12T10:00:00+00:00
```

*(See `examples/02-search-notes.png`)*

---

### Dialog 3 — Read all notes via resource

**User:** Show me all my notes.

**Claude:** *(reads resource `notes://all`)* Here are all your notes:

```json
[
  {
    "id": "n_3f7a1b",
    "title": "Sprint planning",
    "content": "Review backlog, set capacity, assign stories",
    "tags": ["work", "planning"],
    "created_at": "2026-06-12T10:00:00+00:00",
    "updated_at": "2026-06-12T10:00:00+00:00"
  }
]
```

*(See `examples/03-resource-read.png`)*

---

## Local Development & Testing

**MCP Inspector** (no Claude Desktop needed):

```bash
mcp dev homework-mcp/server.py
```

Opens a browser-based inspector where you can call tools and read resources interactively.

**Install into Claude Desktop via CLI:**

```bash
mcp install homework-mcp/server.py --name notes
```

**Smoke-test the store directly:**

```python
from notes_store import NotesStore
from pathlib import Path

s = NotesStore(path=Path("/tmp/test_notes.json"))
note = s.add("Test", "Hello world", tags=["test"])
print(s.get(note["id"]))
print(s.search("hello"))
s.delete(note["id"])
```

---

## Known Limitations

- **Single-user, local only** — no network transport, no multi-user support.
- **No authentication** — anyone who can run the process can read/write all notes.
- **Substring search only** — no semantic/vector search; matches must be literal substrings.
- **No file locking** — concurrent writes from two processes could corrupt `notes.json`.
- **Stateless transport** — each Claude Desktop session spins up a fresh process; the JSON file is the only persistence.
- **No pagination** — `search_notes` is capped by `limit` (default 10); `notes://all` returns the full dataset regardless of size.
- **No undo** — `delete_note` is permanent; there is no recycle bin or history.
