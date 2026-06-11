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
