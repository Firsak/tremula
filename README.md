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

#### Quick start

Four commands to a working vault — no API key, nothing else required:

```bash
uv tool install tremula-mcp        # install (pip install tremula-mcp also works)
cd ~/code/your-project             # your repository
tremula registry init             # create + register tremula-vault/
tremula bootstrap --brief         # seed it from your code (instant, no API key)
```

Then save a `.mcp.json` in the repo root and restart your session:

```json
{ "mcpServers": { "tremula": { "command": "tremula", "args": ["serve"] } } }
```

That's the reactive loop live — your agent now has the six memory tools. For
richer seeding, a stable project name, build-dir filtering, or the ambient
auto-distill loop, follow the full setup below.

#### Full setup

**1 · Install**

```bash
uv tool install tremula-mcp        # or: pip install tremula-mcp
                                   # zero-install: uvx tremula-mcp <cmd>
```

**2 · Register the project**

```bash
cd ~/code/your-project
tremula registry init
```

Creates `tremula-vault/` (with its `_index.md`) and registers the repo. The
project key defaults to the directory name — to pin a stable one (e.g.
`webapp_frontend` instead of `frontend`):

```bash
tremula registry init --name webapp_frontend
```

You can also set the key via the `TREMULA_PROJECT` env var (including in
`.mcp.json`'s `env` block, so the server and the registry agree), and rename
later with `registry init --name <new> --force`.

**3 · Keep build output out** *(big or JS/TS repos)*

`bootstrap` already skips `node_modules`, `.venv`, build dirs, and Tremula's own
state. For framework build output, add a `.tremulaignore` at the repo root —
one directory name per line — *before* seeding, so artifacts don't crowd real
source out of the vault:

```
.next
.sst
.open-next
```

(A machine-wide default is also available via `bootstrap_skip_dirs` in
`~/.tremula/config.yaml`.)

**4 · Seed the vault — brief, full, or partial**

Choose how much to generate up front:

| Mode | Command | What you get |
|---|---|---|
| **Brief** — *recommended* | `tremula bootstrap --brief` | The whole repo as stub notes from docstrings + the tree-sitter AST. **Instant, zero LLM calls, no API key.** The ambient distiller fills notes in as you work. |
| **Full** | `tremula bootstrap` | The whole repo with one LLM call per module for richer summaries. Costs calls and time — run `tremula bootstrap --dry-run` first to preview the count. |
| **Partial** | `tremula bootstrap src/ app/` | Only the directories you name (add `--brief` for stubs). Best for large repos and monorepos. |

Deep-enrich any target later with `tremula bootstrap src/core/`. Full and partial
runs need a model provider — Tremula auto-detects your agent CLI, see
[Choosing the model provider](#choosing-the-model-provider); brief needs nothing.

**5 · Wire the MCP server**

Save this as `.mcp.json` in the repo root — it exposes the six memory tools to
your agent:

```json
{ "mcpServers": { "tremula": { "command": "tremula", "args": ["serve"] } } }
```

**6 · Add the ambient loop** *(optional, recommended)*

Copy `examples/claude-settings.json` into `.claude/settings.json`. Every hook
just runs `tremula hook <Event>`; together they capture sessions, inject the
index, attach relevant notes, and distill durable knowledge in the background.

Restart the session and approve the server + hooks when prompted. (Mute the
ambient loop any time with `TREMULA_HOOKS_DISABLED=1`.)

### Or ask your agent

Paste this into Claude Code (or any agent with shell access) inside your
project:

> Set up Tremula code-memory here. Install it with `uv tool install tremula-mcp`.
> **Before running anything that writes, ask me three things and wait for my
> answers:**
> 1. **Project key** — default is this directory's name (`<dir>`). Suggest a
>    stable, unambiguous key if the dir name is generic (e.g. `webapp_frontend`
>    rather than `frontend`).
> 2. **Bootstrap mode** — how should I seed the vault? Offer these three and
>    recommend one based on repo size:
>    - **brief** — whole repo, zero-LLM stubs (docstrings + AST), instant, no
>      API key. The best default; the distiller enriches notes as I work.
>    - **full** — whole repo, one LLM call per module (richer, costs calls and
>      time). I'll show you the call count first and confirm before running it.
>    - **partial** — only specific dirs (e.g. `src/`, `app/`), brief or full.
>      Recommended for a large repo or monorepo.
> 3. **Ignores** — gather build-output dir candidates two ways: read any
>    existing ignore files (`.gitignore`, `.dockerignore`, `.npmignore`,
>    `.eslintignore`, …) for already-declared dirs, and scan the tree for
>    common ones (`.next`, `.sst`, `.open-next`, `dist`, `build`, `coverage`).
>    Drop those already covered by the defaults, show me the rest, and confirm
>    before writing a repo-root `.tremulaignore` (one dir name per line). This
>    keeps generated files out of the vault.
>
> Then, using my answers: run `tremula registry init` (add `--name <key>` if I
> chose a custom one), then bootstrap in the mode I picked — `tremula bootstrap
> --brief` (brief), `tremula bootstrap` (full, after I confirm the call count),
> or `tremula bootstrap [--brief] <dirs>` (partial). Create `.mcp.json`
> registering an MCP server named `tremula` with
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
