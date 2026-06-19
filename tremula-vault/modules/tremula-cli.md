---
confirmation_count: 0
scope: backend
source: distilled
status: ratified
subject_paths:
- src/tremula/cli.py
subject_symbols:
- tremula.cli.build_parser
- tremula.cli.main
type: module
---

# tremula.cli

CLI entry point for Tremula code-memory system. Provides commands to inspect vaults, manage the project registry, index notes, distill captured sessions into vault updates, and run the MCP server.

## Public API
- `build_parser()` — Create and return the argument parser for all Tremula CLI commands
- `main()` — Entry point for the tremula command-line application

## Key commands

- `tremula bootstrap [--brief] [targets...]` — Generate vault from codebase. `--brief` skips LLM and creates stubs from docstrings + AST (fast for large repos). Optional positional `targets...` (file paths, directories, or dotted module names) trigger focused mode: matched modules get full LLM treatment, rest stay stubs/ambient. Errors if no modules match targets.
- `tremula root add <name> --members <project1>,<project2> [--path <path>] [--force]` — Create a bridge vault connecting specified member projects. Validates all members exist in registry, enforces >=2 members and no key collisions, creates root vault directory, makes root visible in members' mount sets immediately.
- `tremula verify [--prune] [--lower] [--ratify]` — Reconcile note lifecycle against the working tree. With no flags it is read-only: reports provisional notes whose subject code is absent. `--prune` deletes notes whose subject code is gone, `--lower` lowers trust, `--ratify` confirms. This is the **sole** command that deletes or lowers note trust — the inject gate only *suppresses* (injection-scope only, notes stay searchable). Run when the user declares the current code state canonical. See [[decisions/decision-branch-aware-memory-scoping-via-lifecycle-accrual-not-branch-identity]].
