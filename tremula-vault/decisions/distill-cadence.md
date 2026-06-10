---
type: decision
scope: shared
depends_on:
- memory://tremula/decisions/distiller-safety
---

# Decision: distill cadence — debounce, incremental offsets, per-session lock

**Context:** The plan assumed distillation happens "on Stop / PreCompact /
SessionEnd" as if those were rare. In reality Claude Code fires **Stop after
every assistant turn**. Naively that means one `claude -p` call per turn,
re-distilling the entire session each time, with overlapping runs racing each
other and the vault.

**Decision:** Three mechanisms bound the cadence (`distiller.py`):

1. **Byte-offset sidecar** (`<session>.distill.json`): each run consumes only
   events appended since the previous run (`read_session_since`). Nothing is
   distilled twice; an empty increment exits without an LLM call.
2. **Per-session pid lockfile** (`<session>.distill.lock`): two distillers
   never run concurrently for one session; stale locks from dead processes are
   broken automatically.
3. **Minimum interval for Stop** (`distill_min_interval_s`, default 600s):
   Stop-triggered runs are debounced; **PreCompact and SessionEnd bypass the
   interval** (final flush so nothing is lost at session end).

The hook side checks all three cheaply (`should_distill`) *before* spawning a
process — fail closed: a broken check must not cost a `claude -p` call.

**Why:** Cost control (≤1 distill per 10 min per session instead of per turn),
no duplicated knowledge extraction, no racing writers. Capture stays per-event
and free; only the LLM step is rationed.

**Consequences:** Session knowledge lands in the vault with up to one
interval's delay during active work, and immediately at PreCompact/SessionEnd.
Capture payloads are clipped at write time (`clip_payload`) and the distiller
prompt keeps only the newest events within a char budget — very long
increments age out oldest-first.
