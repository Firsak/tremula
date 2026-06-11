---
description: Bootstrap the Tremula vault for this project (tree-sitter scan + LLM summaries)
---

# /tremula-init — bootstrap this project's memory vault

Copy this file to `.claude/commands/tremula-init.md` in a project (or
`~/.claude/commands/` for all projects) to get the `/tremula-init` command.

When invoked, follow these steps:

1. If the project is not registered yet, run `tremula registry init` first
   (requires a `tremula-vault/` directory or creates the registry entry for it).
2. Show the plan and cost before spending tokens:

   ```bash
   tremula bootstrap --dry-run
   ```

   Report to the user: how many modules, which key functions, and how many LLM
   calls the run will make (one per module + one for functions + one for
   conventions, via the configured provider — `claude -p` by default).
3. On the user's confirmation, run:

   ```bash
   tremula bootstrap
   ```

4. Summarize the log: how many module/function/convention notes were written,
   anything skipped (manual-note collisions are protected by design), and
   remind the user that generated notes appear under the auto-section of
   `tremula-vault/_index.md` for review — moving a link up endorses it.

Useful flags: `--max-modules N`, `--functions K`. All generated notes carry
`source: distilled`; re-running updates them in place (idempotent).

**Big repos:** full bootstrap costs one LLM call per module. The recommended
flow is tiered:

1. `tremula bootstrap --brief` — ZERO LLM calls: module stubs from docstrings
   + AST symbols, with the same exact dependency links.
2. `tremula bootstrap <target> [...]` — the user chooses where to focus: deep
   LLM enrichment for specific files, directories, or dotted modules
   (e.g. `tremula bootstrap src/core/billing/ pkg.auth`). Focused runs skip
   the project-wide conventions pass and link beyond the selection (dangling
   links resolve as the vault fills in).
3. Everything else enriches ambiently: the distiller updates stubs in place as
   sessions touch each module. A later full `tremula bootstrap` upgrades all
   remaining stubs idempotently.
