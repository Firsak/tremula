# Tremula

> *Populus tremuloides* — the quaking aspen. The Pando colony is thousands of
> trunks sharing one living root system. Tremula gives your codebases the same
> shape of memory: one knowledge graph per project, connected at the roots
> where projects actually meet.

**Tremula is self-maintaining memory for AI-assisted development.** It keeps an
Obsidian-compatible markdown knowledge graph about your codebase — modules, key
functions, architectural decisions, conventions, cross-service contracts — and
maintains it automatically while you work.

## Why

AI coding agents start every session amnesiac, and hand-written docs rot.
Tremula closes both gaps with two cooperating loops:

- **Reactive — an MCP server** exposing six tools to any MCP client:
  `search`, `get_context` (a topic *plus* its graph neighbors), `read_note`,
  `write_note`, `link_notes`, `split_note`.
- **Ambient — lifecycle hooks** that work without being asked: capture session
  events to a cheap local log, inject the vault's index at session start,
  silently attach the few notes relevant to the files being touched, and
  distill durable knowledge (decisions, conventions, contracts) into notes in
  a debounced background process.

Retrieval is a funnel, never a dump: a ~2k-token index at session start,
graph-expanded context on demand, small working-context attachments per prompt.
Context overhead stays constant no matter how large the vault grows.

## How the vault gets built and maintained

| Mechanism | When | Cost |
|---|---|---|
| `tremula bootstrap --brief` | once, instant | zero LLM — docstrings + tree-sitter AST |
| `tremula bootstrap [target ...]` | wherever you choose to go deep | ~one small LLM call per module |
| background distiller | as you work (debounced, ≥10 min apart) | one small LLM call per run |
| revision janitor | every 5th distill run or `tremula revise` | splits oversized notes, merges duplicates, archives stale ones |

Module dependency links come from the tree-sitter import graph — computed,
never hallucinated. The distiller's LLM is configurable (`claude -p` under a
subscription by default; Anthropic API or a local model via one config line).

## Safety model

- **Markdown is the source of truth.** SQLite/FTS5 is a rebuildable cache.
  Edit notes in Obsidian or any editor; changes are picked up automatically.
- **Hand-written notes are protected.** Machine writes are marked
  `source: distilled`. The distiller updates its own notes freely but may only
  *enrich* yours — through an LLM judge plus a deterministic
  no-content-loss backstop.
- **Projects are isolated by construction.** A session resolves its own vault
  plus explicitly declared shared vaults (`roots`) — any other address is
  unresolvable, not merely filtered.
- **Nothing is deleted.** Cleanup archives to `attic/` inside the vault, with
  git history as the deeper tombstone.
- Hooks are fail-silent and never slow a session. Kill switch:
  `TREMULA_HOOKS_DISABLED=1`.

## Federation

Connect repositories where they actually meet:

```bash
tremula root add webapp-api --members webapp,api
```

Shared contracts live in the bridge vault as one note per endpoint with a
section per side (`## Provider (api)` / `## Consumer (webapp)`). Each project's
tooling can only edit its own section — so when the sides disagree, the drift
is visible in one file instead of hidden between two repos.

## Quickstart

```bash
# install (PyPI release planned; from source for now)
git clone https://github.com/Firsak/tremula && cd tremula && uv sync

cd ~/code/your-project
uv run tremula registry init          # register the project
uv run tremula bootstrap --brief      # instant zero-LLM vault; add targets later
```

For Claude Code, in your project: copy `examples/mcp.json` → `.mcp.json` (the
MCP tools) and merge `examples/claude-settings.json` into
`.claude/settings.json` (the ambient loop). Open `tremula-vault/` in Obsidian
for the graph view. Machine-written notes queue in the auto-section of
`_index.md`; moving a link up into your curated headings endorses it.

## Client support

The server speaks standard MCP over stdio — Claude Code, Cursor, Codex, Gemini
CLI, or anything else that talks MCP. The ambient loop ships wired for Claude
Code's hook lifecycle; any host that can run a command on lifecycle events can
drive the same `tremula hook <event>` CLI.

## Status

Core complete and self-hosting: this repository's own vault is maintained by
Tremula, and roughly three quarters of its notes were written by the system
while the system was being written. 220+ tests, `ruff`-clean.

Roadmap: PyPI release · hybrid semantic search (sqlite-vec) · long-lived HTTP
daemon · native file watcher.

## Develop

```bash
uv sync --extra dev
uv run pytest                  # TREMULA_LIVE_TESTS=1 uv run pytest -m live for real-LLM tests
uv run ruff check src tests
```

MIT.
