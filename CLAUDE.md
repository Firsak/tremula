# Tremula

Code-memory MCP for Claude Code: an Obsidian-compatible markdown note graph
about a codebase (`ramet`), federated across projects (`genet`) via a registry
and bridge vaults (`roots`), maintained by a **reactive** MCP-server layer and
an **ambient** hooks layer.

- Language: Python 3.12+ · MCP via FastMCP · `python-frontmatter` · stdlib
  `sqlite3` + FTS5 · PyYAML + pydantic · tooling: `uv`, `ruff`, `pytest`.
- Source of truth: markdown in `tremula-vault/`. SQLite index is rebuildable cache.
- Status: **core complete** (plan stages 1–7 built, tested, dogfooded; FTS5-only).
  Roadmap: PyPI release, sqlite-vec hybrid search, HTTP daemon, native watcher.

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

## Memory system (dogfooding, automated parts)
- Ambient hooks are wired in `.claude/settings.json`: sessions are captured to
  NDJSON and distilled on Stop (debounced, ≥10 min apart) / PreCompact /
  SessionEnd. Kill switch: `TREMULA_HOOKS_DISABLED=1`.
- MCP server template: `examples/mcp.json` → copy to `.mcp.json` to get the
  `search` / `get_context` / `read_note` / `write_note` / `link_notes` /
  `split_note` tools. Prefer `search`/`get_context` over reading
  `tremula-vault/` files directly once registered.
- Distilled notes carry `source: distilled`; hand-written notes are protected
  (judged enrichment only — see [[decisions/distiller-safety]]).

## Conventions
- `ruff` for lint/format; tests in `tests/` run with `pytest` (or `uv run pytest`).
- Code, comments, and docs are **English** (the source plan is Russian — reference only).
- Live-LLM tests are opt-in: `TREMULA_LIVE_TESTS=1 uv run pytest -m live`.
