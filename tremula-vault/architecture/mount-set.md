---
type: architecture
scope: shared
depends_on: [memory://tremula/conventions/memory-uri-addressing]
---

# Mount set: what a session can see

A session's **mount set** is the `key -> vault root` map it is allowed to read:
its own ramet plus every `root` it is a member of. Everything else is invisible
— not in search, not in graph traversal, not in injection.

Resolution (`src/tremula/registry.py`):
1. `resolve_session(cwd)` loads the registry and calls `find_project_by_cwd` —
   the project whose `repo`/vault directory contains cwd (longest match wins for
   nested checkouts).
2. `Registry.mount_set(project)` returns `{project: ramet_path}` plus every
   `root` whose `members` include the project.
3. That map is fed directly to `memory_uri.resolve` — a `memory://` URI for a
   project outside the set raises `MemoryURIError`, so the boundary is enforced
   at resolution time, not by filtering after the fact.

Example: a session in `webapp` sees `webapp` + root `webapp-api`, but never the
internals of `api`. `api` participates in the same root, so both sides reach the
shared contract notes without seeing each other's private notes.

The registry lives at `~/.tremula/registry.yaml` (override:
`TREMULA_REGISTRY`). Projects and roots share one key namespace; a key cannot be
both.
