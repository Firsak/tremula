---
scope: shared
source: distilled
type: module
---

# tremula

Code-memory MCP server for Claude Code. Provides an Obsidian-compatible markdown vault describing a codebase, federated across projects via a registry and bridge vaults, with auto-maintenance via Claude Code hooks. Markdown is source of truth; SQLite index is a rebuildable cache.

## Public API
- `__version__` — Package version string
