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
never hallucinated. The distiller is **agent-agnostic**: by default it
auto-detects whichever agent CLI you already have on `PATH` (`claude`, `gemini`,
`codex`, …) and shells out to it — no API key, no vendor lock-in. Point it at a
specific CLI, an explicit command, or the Anthropic API in one config line (see
[Choosing the model provider](#choosing-the-model-provider)).

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
tremula registry init            # creates tremula-vault/ + registers the project
                                 # name it: registry init --name webapp_frontend

# Big or JS/TS repo? List build-output dirs in .tremulaignore (see below) BEFORE
# bootstrapping — otherwise they crowd real source out under the module cap.
tremula bootstrap --brief        # instant zero-LLM vault (whole project)
# or scope it to where the code lives:   tremula bootstrap src/ app/
# later, deep-enrich where it matters:   tremula bootstrap src/core/
```

The project key defaults to the directory name. To pin a stable key (e.g.
`webapp_frontend` rather than `frontend`), pass `--name`, or set
`TREMULA_PROJECT` — including in `.mcp.json`'s `env` block, so the server and
the registration agree. Re-running `registry init --name <new> --force` from a
registered repo renames it.

`bootstrap` prunes `node_modules`, `.venv`, build output, and Tremula's own
state by default. For project-specific build dirs, drop a `.tremulaignore` at
the repo root — one directory name per line, committed with the project:

```
.next
.sst
.open-next
```

(A machine-wide default is also available via `bootstrap_skip_dirs` in
`~/.tremula/config.yaml`.)

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

> Set up Tremula code-memory here. Install it with `uv tool install tremula-mcp`.
> **Before running anything that writes, ask me three things and wait for my
> answers:**
> 1. **Project key** — default is this directory's name (`<dir>`). Suggest a
>    stable, unambiguous key if the dir name is generic (e.g. `webapp_frontend`
>    rather than `frontend`).
> 2. **Scope** — bootstrap the whole repo, or focus on specific source dirs
>    (e.g. `src/`, `app/`)? Recommend focusing for a large repo.
> 3. **Ignores** — gather build-output dir candidates two ways: read any
>    existing ignore files (`.gitignore`, `.dockerignore`, `.npmignore`,
>    `.eslintignore`, …) for already-declared dirs, and scan the tree for
>    common ones (`.next`, `.sst`, `.open-next`, `dist`, `build`, `coverage`).
>    Drop those already covered by the defaults, show me the rest, and confirm
>    before writing a repo-root `.tremulaignore` (one dir name per line). This
>    keeps generated files out of the vault.
>
> Then, using my answers: run `tremula registry init` (add `--name <key>` if I
> chose a custom one), then `tremula bootstrap --brief` (append the focus dirs if
> I scoped it). Create `.mcp.json` registering an MCP server named `tremula` with
> stdio command `tremula serve` (add an `env.TREMULA_PROJECT` set to my key if it
> differs from the dir name). In `.claude/settings.json`, add hooks running
> `tremula hook <Event>` for SessionStart, UserPromptSubmit, PostToolUse, Stop,
> PreCompact, and SessionEnd. Finally, show me the resulting vault note count and
> ask me to restart the session.

Open `tremula-vault/` in Obsidian for the graph view. Machine-written notes
queue in the auto-section of `_index.md`; moving a link up into your curated
headings endorses it.

Working from a source checkout instead? `git clone … && uv sync`, then use
`uv run tremula …` and point `.mcp.json`/hook commands at `.venv/bin/tremula`
(this repo's own `.mcp.json` shows the pattern).

## Choosing the model provider

Bootstrap (full mode) and the background distiller need an LLM. Tremula is
**agent-agnostic** and ships with no vendor default — set `provider` in
`~/.tremula/config.yaml`:

```yaml
# Default: auto-detect an agent CLI on PATH (claude / gemini / codex / …) and
# shell out to it. No API key. If several are installed, pin one with `agent`.
provider:
  kind: auto
  # agent: claude        # optional: pin when multiple CLIs are present

# Pin a specific agent CLI by name:
# provider: { kind: cli, agent: gemini }

# Or run any one-shot CLI completer. "{prompt}" => prompt as an arg; omit it and
# the prompt is piped on stdin. "{model}" => the `model` field below.
# provider:
#   kind: cli
#   command: ["llm", "-m", "gpt-4o-mini", "{prompt}"]

# Or the Anthropic API (the only path that needs a key):
# provider:
#   kind: anthropic
#   model: claude-haiku-4-5-20251001
#   auth_env: ANTHROPIC_API_KEY        # read from this env var
#   # base_url: http://localhost:8080  # Anthropic-compatible local endpoint
```

`auto` needs no key — it uses whatever your installed CLI is already
authenticated with. Only `kind: anthropic` reads `auth_env`. `bootstrap --brief`
makes **zero** LLM calls, so it needs no provider at all.

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
