---
depends_on:
- memory://tremula/decisions/vault-at-repo-root
- memory://tremula/architecture/two-loops
scope: backend
source: distilled
type: decision
---

# Decision: Index freshness via mtime revalidation, not dirty flags

**Context:** The vault markdown is written by multiple agents: manual edits in Obsidian, the distiller, parallel sessions, and the MCP server. The SQLite index must stay fresh without tight coordination.

**Alternatives rejected:**
1. Dirty-flag file: writers touch a marker to signal staleness. Fails because manual editors (Obsidian) don't cooperate.
2. File watcher (inotify/FSEvents): instant invalidation, but complex and hard to debug — deferred to Stage 8.
3. **mtime revalidation (chosen):** at query time, scan vault dirs and check file mtimes against the index; reparse and upsert newer files, delete missing ones.

**Decision:** Use pull-based mtime revalidation. Cost: ~1–2 ms per query at scale (one `stat()` per note). Universal coverage: Markdown stays the only source of truth; all writers cooperate automatically, zero coordination. Aligns with "SQLite is a rebuildable cache."

**How to apply:** Before `search()`, `get_context()`, and `read_note()`, call `Index.refresh(mounts)`: scan vault dirs using `os.scandir`, compare file mtimes/sizes against cached metadata, upsert newer files, delete missing ones. Combine mtime *and* file size checks to handle second-level granularity edge cases.

**Honest limit:** mtime granularity (typically 1 second) means an edit within the same second as the last index write could theoretically be missed. File size comparison mitigates. Dogfooding will reveal if this ever matters in practice.

The file-watcher upgrade (Stage 8, Rust watcher, instant invalidation) is the natural next step if polling becomes a bottleneck.
