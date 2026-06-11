---
depends_on:
- memory://tremula/modules/tremula-capture
- memory://tremula/modules/tremula-config
- memory://tremula/modules/tremula-distiller
- memory://tremula/modules/tremula-index
- memory://tremula/modules/tremula-index-md
- memory://tremula/modules/tremula-injection
- memory://tremula/modules/tremula-registry
- memory://tremula/modules/tremula-vault
- memory://tremula/modules/tremula-workctx
scope: shared
source: distilled
type: module
---

# tremula.hooks

Ambient hook dispatcher for Claude Code events. Routes capture events to session NDJSON, injects context at SessionStart, and spawns async distiller on Stop/PreCompact/SessionEnd to update the vault.

## Public API
- `run_hook(event: str, payload: dict | None = None) -> int` — Handle one hook event from Claude Code; always returns 0. Routes to capture, injection, or distillation based on event type.
- `CAPTURE_EVENTS` — Set of event types that should be appended to session NDJSON (PostToolUse, PreToolUse, UserPromptSubmit, Stop, Notification).
- `DISTILL_EVENTS` — Set of event types that trigger async distiller spawn (Stop, PreCompact, SessionEnd).
