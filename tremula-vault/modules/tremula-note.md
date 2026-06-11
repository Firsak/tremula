---
depends_on:
- memory://tremula/modules/tremula-memory-uri
scope: shared
source: distilled
type: module
---

# tremula.note

Defines the atomic unit of a knowledge vault: a markdown note with YAML frontmatter. Validates note metadata (type, scope, typed relations to other notes) via pydantic and provides loaders to parse notes with automatic or explicit vault root discovery.

## Public API
- `NoteType` — Enum of valid note types: module, function, convention, decision, architecture, contract, index
- `Scope` — Enum of scope values for filtering: backend, frontend, shared
- `NoteFrontmatter` — Pydantic model validating note frontmatter: type, scope, source (manual/distilled), typed links
- `Note` — Parsed note with URI, validated frontmatter, markdown body, title property, and linked_uris() method
- `load_note(path: str | Path, project: str) -> Note` — Load and validate a note file, auto-discovering vault root by walking up to a tremula-vault directory
- `load_note_in_vault(path: str | Path, vault_root: str | Path, project: str) -> Note` — Load a note with explicit vault root, deriving its memory:// URI from the relative path
- `RELATIONS` — Constant tuple of allowed typed relation keys in links: depends_on, implements, decided_in, part_of
