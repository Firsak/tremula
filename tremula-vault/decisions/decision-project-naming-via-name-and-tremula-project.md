---
depends_on:
- memory://tremula/modules/tremula-cli
- memory://tremula/modules/tremula-registry
scope: backend
source: distilled
type: decision
---

# Decision: Project naming via --name and TREMULA_PROJECT

**Problem:** Early releases tied project identity to directory name. When a project moves or is cloned into a different location, the identity would change, breaking links and mount-set consistency. Also, local names are often long or provisional; release names are shorter and stable.

**Decision:** Project registry key is now decoupled from directory name and explicitly configurable:

1. **At registration:** `tremula registry init --name <key>` (or `TREMULA_PROJECT=<key> tremula init`)
2. **At MCP runtime:** `TREMULA_PROJECT` env var overrides the registered key (allows one MCP server to serve different keys in different sessions)
3. **Rename existing:** `tremula registry init --name <new-key> --force` to update an existing project's key

**Why:** Stable, human-chosen identity independent of file system layout. Enables federation workflows where the same code may be part of different projects in different contexts.

**How to apply:** Document in README and examples that TREMULA_PROJECT is the way to pin a stable key for MCP. Show in examples/mcp.json how to set it. Enforce that key must be registered before use (serve will fail if not found).
