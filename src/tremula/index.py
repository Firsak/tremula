"""The SQLite/FTS5 index — a rebuildable cache over the markdown vaults.

Markdown is the source of truth; this index exists so search and graph
traversal do not re-read every file. It is always reconstructable from the
notes (``rebuild``) and is never committed to git.

Three tables:
- ``notes``     — one row per note: metadata + scope (for monorepo filtering).
- ``notes_fts`` — FTS5 full-text over title + body, keyed by ``uri``.
- ``links``     — the typed graph: ``(src, relation, dst)`` rows from frontmatter.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .note import Note, load_note_in_vault

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    uri     TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    type    TEXT NOT NULL,
    scope   TEXT NOT NULL,
    title   TEXT NOT NULL,
    mtime   REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    uri UNINDEXED, title, body, tokenize = 'porter unicode61'
);
CREATE TABLE IF NOT EXISTS links (
    src      TEXT NOT NULL,
    relation TEXT NOT NULL,
    dst      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst);
CREATE INDEX IF NOT EXISTS idx_notes_scope ON notes(scope);
"""


@dataclass
class SearchHit:
    uri: str
    title: str
    type: str
    scope: str
    snippet: str
    rank: float


class Index:
    """A SQLite-backed index over one mount set's vaults."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Index:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- writes -------------------------------------------------------------

    def upsert_note(self, note: Note, body: str, mtime: float) -> None:
        uri = str(note.uri)
        self.delete_note(uri)  # idempotent replace
        self.conn.execute(
            "INSERT INTO notes(uri, project, type, scope, title, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uri, note.uri.project, note.frontmatter.type.value,
             note.frontmatter.scope.value, note.title, mtime),
        )
        self.conn.execute(
            "INSERT INTO notes_fts(uri, title, body) VALUES (?, ?, ?)",
            (uri, note.title, body),
        )
        for relation, targets in note.frontmatter.links.items():
            for dst in targets:
                self.conn.execute(
                    "INSERT INTO links(src, relation, dst) VALUES (?, ?, ?)",
                    (uri, relation, dst),
                )
        self.conn.commit()

    def delete_note(self, uri: str) -> None:
        self.conn.execute("DELETE FROM notes WHERE uri = ?", (uri,))
        self.conn.execute("DELETE FROM notes_fts WHERE uri = ?", (uri,))
        self.conn.execute("DELETE FROM links WHERE src = ?", (uri,))
        self.conn.commit()

    def rebuild(self, mounts: dict[str, Path]) -> int:
        """Drop everything and repopulate from every vault in the mount set."""
        self.conn.executescript(
            "DELETE FROM notes; DELETE FROM notes_fts; DELETE FROM links;"
        )
        count = 0
        for key, vault_root in mounts.items():
            vault_root = Path(vault_root)
            if not vault_root.is_dir():
                continue
            for path in sorted(vault_root.rglob("*.md")):
                note = load_note_in_vault(path, vault_root, project=key)
                self.upsert_note(note, body=note.body, mtime=path.stat().st_mtime)
                count += 1
        return count

    # ---- reads --------------------------------------------------------------

    def search(self, query: str, scope: str | None = None, limit: int = 10) -> list[SearchHit]:
        """Full-text search within the index, optionally filtered by scope."""
        sql = (
            "SELECT n.uri, n.title, n.type, n.scope, "
            "       snippet(notes_fts, 2, '[', ']', ' … ', 12) AS snippet, "
            "       bm25(notes_fts) AS rank "
            "FROM notes_fts JOIN notes n ON n.uri = notes_fts.uri "
            "WHERE notes_fts MATCH ? "
        )
        params: list = [query]
        if scope is not None:
            sql += "AND n.scope = ? "
            params.append(scope)
        sql += "ORDER BY rank LIMIT ?"
        params.append(limit)
        return [
            SearchHit(r["uri"], r["title"], r["type"], r["scope"], r["snippet"], r["rank"])
            for r in self.conn.execute(sql, params)
        ]

    def neighbors(self, uri: str, depth: int = 1) -> set[str]:
        """URIs reachable from ``uri`` within ``depth`` hops (both directions)."""
        seen: set[str] = set()
        frontier = {uri}
        for _ in range(max(0, depth)):
            nxt: set[str] = set()
            for node in frontier:
                rows = self.conn.execute(
                    "SELECT dst AS x FROM links WHERE src = ? "
                    "UNION SELECT src AS x FROM links WHERE dst = ?",
                    (node, node),
                )
                for r in rows:
                    if r["x"] not in seen and r["x"] != uri:
                        nxt.add(r["x"])
            seen |= nxt
            frontier = nxt
            if not frontier:
                break
        return seen

    def get_meta(self, uri: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM notes WHERE uri = ?", (uri,)).fetchone()

    def all_notes(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM notes ORDER BY mtime DESC"))
