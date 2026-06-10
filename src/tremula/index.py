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

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .note import Note, load_note_in_vault


def _fts_query(text: str) -> str:
    """Reduce arbitrary user text to a safe FTS5 query (word tokens, implicit AND).

    Raw input like ``don't``, ``C++`` or unbalanced quotes is valid text but
    invalid FTS5 syntax and would raise OperationalError mid-tool-call.
    """
    return " ".join(re.findall(r"\w+", text))

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
        # check_same_thread=False: the MCP server and tests may touch the index
        # from worker threads; access is serialized by our call patterns.
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # WAL + busy timeout: a hook (SessionStart rebuild), the MCP server and
        # a detached distiller can hit the same per-project DB concurrently.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Index:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- writes -------------------------------------------------------------

    def upsert_note(self, note: Note, body: str, mtime: float, *, commit: bool = True) -> None:
        uri = str(note.uri)
        self.delete_note(uri, commit=False)  # idempotent replace
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
        if commit:
            self.conn.commit()

    def delete_note(self, uri: str, *, commit: bool = True) -> None:
        self.conn.execute("DELETE FROM notes WHERE uri = ?", (uri,))
        self.conn.execute("DELETE FROM notes_fts WHERE uri = ?", (uri,))
        self.conn.execute("DELETE FROM links WHERE src = ?", (uri,))
        if commit:
            self.conn.commit()

    def rebuild(self, mounts: dict[str, Path]) -> int:
        """Drop everything and repopulate from every vault in the mount set.

        Runs as one transaction: concurrent readers never observe a half-built
        index, and N notes don't cost N commits.
        """
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
                self.upsert_note(
                    note, body=note.body, mtime=path.stat().st_mtime, commit=False
                )
                count += 1
        self.conn.commit()
        return count

    # ---- reads --------------------------------------------------------------

    def search(self, query: str, scope: str | None = None, limit: int = 10) -> list[SearchHit]:
        """Full-text search within the index, optionally filtered by scope."""
        fts = _fts_query(query)
        if not fts:
            return []
        sql = (
            "SELECT n.uri, n.title, n.type, n.scope, "
            "       snippet(notes_fts, 2, '[', ']', ' … ', 12) AS snippet, "
            "       bm25(notes_fts) AS rank "
            "FROM notes_fts JOIN notes n ON n.uri = notes_fts.uri "
            "WHERE notes_fts MATCH ? "
        )
        params: list = [fts]
        if scope is not None:
            sql += "AND n.scope = ? "
            params.append(scope)
        sql += "ORDER BY rank LIMIT ?"
        params.append(limit)
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # A query FTS5 still cannot parse must degrade to "no hits", never
            # crash a tool call mid-session.
            return []
        return [
            SearchHit(r["uri"], r["title"], r["type"], r["scope"], r["snippet"], r["rank"])
            for r in rows
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
