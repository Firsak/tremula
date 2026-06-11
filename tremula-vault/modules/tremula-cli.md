---
depends_on:
- memory://tremula/modules/tremula
- memory://tremula/modules/tremula-config
- memory://tremula/modules/tremula-distiller
- memory://tremula/modules/tremula-hooks
- memory://tremula/modules/tremula-index
- memory://tremula/modules/tremula-note
- memory://tremula/modules/tremula-registry
- memory://tremula/modules/tremula-server
- memory://tremula/modules/tremula-vault
scope: shared
source: distilled
type: module
---

# tremula.cli

CLI entry point for Tremula code-memory system. Provides commands to inspect vaults, manage the project registry, index notes, distill captured sessions into vault updates, and run the MCP server.

## Public API
- `build_parser()` — Create and return the argument parser for all Tremula CLI commands
- `main()` — Entry point for the tremula command-line application
