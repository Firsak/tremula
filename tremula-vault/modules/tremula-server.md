---
depends_on:
- memory://tremula/modules/tremula-config
- memory://tremula/modules/tremula-index
- memory://tremula/modules/tremula-registry
- memory://tremula/modules/tremula-vault
scope: shared
source: distilled
type: module
---

# tremula.server

Reactive MCP layer exposing six note-management tools via FastMCP (stdio). Resolves the current project at startup, builds the mount-set index, and binds tools to VaultService for read/write/search/graph operations.

## Public API
- `build_server(vault: VaultService) -> FastMCP` — Create and configure FastMCP server with write_note, read_note, search, get_context, link_notes, split_note tools.
- `serve() -> int` — Resolve session, build index, run stdio server; returns 0 on success or 1 if project not registered.
