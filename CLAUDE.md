# Tremula

Code-memory MCP for Claude Code: an Obsidian-compatible markdown note graph
about a codebase (`ramet`), federated across projects (`genet`) via a registry
and bridge vaults (`roots`), maintained by a **reactive** MCP-server layer and
an **ambient** hooks layer.

- Language: Python 3.12+ · MCP via FastMCP · `python-frontmatter` · stdlib
  `sqlite3` + FTS5 · PyYAML + pydantic · tooling: `uv`, `ruff`, `pytest`.
- Source of truth: markdown in `tremula-vault/`. SQLite index is rebuildable cache.
- Scope of this build: **Stages 1–7** (FTS5-only; HTTP/sqlite-vec/Rust = deferred Stage 8).

Full spec: `.omc/specs/deep-interview-tremula.md`. Original plan (Russian, reference only):
`~/Downloads/tremula-architecture-plan.md`.

## Vault maintenance (manual mode — works before any code)

This repo dogfoods Tremula: keep `tremula-vault/` current by hand until the
distiller automates it. When you make a durable choice while working here:

- **A decision** (chose X over Y, and why) → new note in `tremula-vault/decisions/`
- **A convention** (style, naming, a pattern we follow) → `tremula-vault/conventions/`
- **A module's purpose / public API** → `tremula-vault/modules/`
- **A key function worth remembering** (not every function) → `tremula-vault/functions/`
- **A layer or data-flow** → `tremula-vault/architecture/`

Rules:
- One note = one atomic fact. See [[conventions/note-granularity]].
- Frontmatter: `type` (required) + `scope` + typed links. See [[conventions/frontmatter-schema]].
- Link with global `memory://project/path/note` URIs, never local `[[title]]` in
  frontmatter relations. See [[conventions/memory-uri-addressing]].
- Add the note to `_index.md` under the right heading.
- Do NOT record ephemera (PR numbers, SHAs, transient TODOs).

## Conventions
- `ruff` for lint/format; tests in `tests/` run with `pytest` (or `uv run pytest`).
- Code, comments, and docs are **English** (the source plan is Russian — reference only).
