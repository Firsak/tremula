---
scope: shared
source: distilled
type: module
---

# tremula.memory_uri

Parses and resolves global memory:// URIs (memory://project/path/note) for cross-vault note references. Replaces local Obsidian wikilinks with unambiguous global addressing; enables federated vault references via a project registry.

## Public API
- `MemoryURI.parse(raw: str) -> MemoryURI` — Parse a memory:// URI string into project and path components; raise MemoryURIError if malformed
- `MemoryURI.relative_file() -> Path` — Return vault-relative markdown file path for this URI (e.g., decisions/name.md)
- `MemoryURI.note_id` — Property: final path segment (the note's identifier)
- `is_memory_uri(value: str) -> bool` — Check if a string matches memory:// URI syntax
- `resolve(uri: str | MemoryURI, project_roots: dict[str, Path]) -> Path` — Resolve memory:// URI to absolute filesystem path using project-to-vault-root mapping; raise MemoryURIError if project not in mount set or URI escapes vault boundary
- `MemoryURIError` — Exception raised for invalid or unresolvable memory:// URIs
