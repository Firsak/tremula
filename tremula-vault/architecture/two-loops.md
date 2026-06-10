---
type: architecture
scope: shared
depends_on: [memory://tremula/architecture/mount-set]
---

# Two loops: reactive + ambient

Tremula runs on two contours, and that split is the core architectural idea.

**Reactive (MCP server).** `src/tremula/server.py` is a FastMCP stdio server with
six tools — `write_note`, `read_note`, `search`, `get_context`, `link_notes`,
`split_note` — all thin wrappers over `VaultService` (`vault.py`). The agent
calls these when it decides to. Markdown is written first, then the SQLite/FTS5
index (`index.py`) is updated. Everything is scoped to the session's mount set.

**Ambient (hooks).** `src/tremula/hooks.py` (`tremula hook <event>`) fires on
Claude Code lifecycle events without the agent choosing to:
- capture events → cheap NDJSON append (`capture.py`), no LLM, always exit 0;
- `SessionStart` → inject `_index.md` + hot notes (`injection.py`) so memory is
  present from the first token;
- `Stop`/`PreCompact`/`SessionEnd` → spawn a **detached** distiller
  (`distiller.py`) that reads the session NDJSON, asks an LLM (provider
  abstracted — `claude -p` by default) for durable note operations under hygiene
  rules, and applies them through the same `VaultService`.

Why both: an MCP server idles until the model invokes it; hooks always fire. The
reactive loop is precise on demand; the ambient loop guarantees memory is
captured and surfaced even when the agent never thinks to ask.

The distiller and the server share one write path (`VaultService`), so a note
written by a tool and a note written by distillation are indistinguishable.
