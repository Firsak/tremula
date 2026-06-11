---
depends_on:
- memory://tremula/modules/tremula-index
- memory://tremula/modules/tremula-memory-uri
- memory://tremula/modules/tremula-note
scope: shared
source: distilled
type: module
---

# tremula.vault

Write/read/search engine for vault operations, maintaining mount-set-scoped note access with markdown as source of truth and SQLite index as rebuildable cache.

## Public API
- `slugify(text: str) -> str` — Convert text to lowercase hyphenated slug.
- `ContextResult` — Dataclass holding seed hits and graph neighbors for a context query.
- `VaultService(mounts, index, project)` — Mount-set-scoped vault service with optional default project target.
- `VaultService.target_uri(title, type, project) -> str` — Return the memory:// URI a note write would create, without writing.
- `VaultService.write_note(title, content, type, scope, links, project, source, protect) -> str` — Create or overwrite a note (respecting protect=True for manual notes); returns URI.
- `VaultService.link_notes(src, dst, relation) -> str` — Add a typed edge to src's frontmatter; returns src URI.
- `VaultService.split_note(uri) -> list[str]` — Split oversized note by ## sections into child notes.
