---
depends_on:
- memory://tremula/modules/tremula-bootstrap
- memory://tremula/modules/tremula-registry
- memory://tremula/modules/tremula-contracts
scope: backend
source: distilled
type: module
---

# tremula.cli

CLI entry point for Tremula code-memory system. Provides commands to inspect vaults, manage the project registry, index notes, distill captured sessions into vault updates, and run the MCP server.

## Public API
- `build_parser()` — Create and return the argument parser for all Tremula CLI commands
- `main()` — Entry point for the tremula command-line application

## Key commands

- `tremula bootstrap [--brief]` — Generate vault from codebase. `--brief` skips LLM and creates stubs from docstrings + AST (fast for large repos).
- `tremula root add <name> --members <project1>,<project2> [--path <path>] [--force]` — Create a bridge vault connecting specified member projects. Validates all members exist in registry, enforces >=2 members and no key collisions, creates root vault directory, makes root visible in members' mount sets immediately.
