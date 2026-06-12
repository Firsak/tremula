# Tremula

[![PyPI](https://img.shields.io/pypi/v/tremula-mcp)](https://pypi.org/project/tremula-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/tremula-mcp)](https://pypi.org/project/tremula-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

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

## Install & set up

### Manually

```bash
uv tool install tremula-mcp      # or: pip install tremula-mcp
                                 # zero-install alternative: uvx tremula-mcp <cmd>

cd ~/code/your-project
tremula registry init            # register the project
tremula bootstrap --brief        # instant zero-LLM vault
# later, deep-enrich where it matters:  tremula bootstrap src/core/
```

Wire it into Claude Code, inside the project:

```json
{ "mcpServers": { "tremula": { "command": "tremula", "args": ["serve"] } } }
```

— save that as `.mcp.json` (the six memory tools). For the ambient loop
(capture → inject → attach → distill), copy `examples/claude-settings.json`
into `.claude/settings.json` — every hook entry just runs
`tremula hook <Event>`. Restart the session and approve the server + hooks
when asked.

### Or ask your agent

Paste this into Claude Code (or any agent with shell access) inside your
project:

> Set up Tremula code-memory here: install the `tremula-mcp` package with
> `uv tool install tremula-mcp`, run `tremula registry init`, then
> `tremula bootstrap --brief`. Create `.mcp.json` registering an MCP server
> named `tremula` with stdio command `tremula serve`. In
> `.claude/settings.json`, add hooks running `tremula hook <Event>` for
> SessionStart, UserPromptSubmit, PostToolUse, Stop, PreCompact, and
> SessionEnd. Then ask me to restart the session.

Open `tremula-vault/` in Obsidian for the graph view. Machine-written notes
queue in the auto-section of `_index.md`; moving a link up into your curated
headings endorses it.

Working from a source checkout instead? `git clone … && uv sync`, then use
`uv run tremula …` and point `.mcp.json`/hook commands at `.venv/bin/tremula`
(this repo's own `.mcp.json` shows the pattern).

## Client support

The server speaks standard MCP over stdio — Claude Code, Cursor, Codex, Gemini
CLI, or anything else that talks MCP. The ambient loop ships wired for Claude
Code's hook lifecycle; any host that can run a command on lifecycle events can
drive the same `tremula hook <event>` CLI.

## Status

Core complete and self-hosting: this repository's own vault is maintained by
Tremula, and roughly three quarters of its notes were written by the system
while the system was being written. 220+ tests, `ruff`-clean.

Roadmap: hybrid semantic search (sqlite-vec) · long-lived HTTP daemon ·
native file watcher.

## Develop

```bash
uv sync --extra dev
uv run pytest                  # TREMULA_LIVE_TESTS=1 uv run pytest -m live for real-LLM tests
uv run ruff check src tests
```

MIT.
