---
depends_on:
- memory://tremula/modules/tremula-note
scope: shared
source: distilled
type: module
---

# tremula.index

SQLite/FTS5-backed index for fast searching and graph traversal over markdown note vaults. Markdown is the source of truth; the index is a rebuildable cache with three tables: notes (metadata), notes_fts (full-text), and links (typed graph).

## Public API
- `SearchHit(uri, title, type, scope, snippet, rank)` — Search result with FTS rank and context snippet
- `Index(db_path)` — SQLite-backed index; context manager with WAL mode and serialized concurrent access
- `upsert_note(note, body, mtime, size=0, commit=True)` — Add or replace a note, FTS entry, and link rows
- `delete_note(uri, commit=True)` — Remove note, FTS, and all outbound links
- `rebuild(mounts: dict[str, Path]) → int` — Drop and repopulate from all vaults in mount set; atomic; returns count
- `refresh(mounts: dict[str, Path]) → int` — Incremental revalidation by mtime/size; delete vanished notes; returns count
