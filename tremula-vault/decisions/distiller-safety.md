---
type: decision
scope: shared
depends_on:
- memory://tremula/architecture/two-loops
---

# Decision: distiller safety — recursion guard, provenance, judged enrichment

**Context:** The first live run of the ambient loop produced two failures.
(1) A fork bomb: the Stop hook spawned the distiller, whose own `claude -p`
session fired the same hooks, spawning more distillers exponentially. (2) A
clobber: the distiller, blind to existing content, regenerated a thinner
version of a hand-written decision note and overwrote it by slug collision,
losing half its content.

**Decision:** Three coupled safeguards.

1. **Recursion guard.** The spawned distiller runs with
   `TREMULA_HOOKS_DISABLED=1` in its environment; `run_hook` returns
   immediately when the flag is set. The user's session keeps fully working
   hooks; only the distiller's own nested LLM call is muted, so exactly one
   distiller runs per Stop.
2. **Provenance.** Every note carries `source: manual | distilled` in
   frontmatter (missing = `manual`). The distiller writes with
   `source="distilled"` and `protect=True`: it may freely update its own
   notes but cannot blindly overwrite a manual one.
3. **Judged enrichment, not hard rejection.** When a distiller write collides
   with a manual note, an LLM judge sees the original and the proposal and
   decides `enrich` (emitting a full merged body) or `reject`. A
   deterministic backstop (`content_preserved`, ≥85% of the original's
   significant words must survive) blocks the merge even if the judge
   approves a lossy one. Enriched notes stay `source: manual` — the human
   still owns them.

**Why:** Blind overwrites lose knowledge; blanket bans lose enrichment. The
judge restores the upside (the distiller can genuinely improve a note) while
the deterministic backstop caps the downside (no silent content loss, even
with a misbehaving model). The distiller is also shown existing notes in its
prompt (read-before-write), so it updates in place instead of spawning thin
duplicates.

**Consequences:** One `claude -p` call per Stop plus one judge call per
manual-note collision. Hook wiring for this repo lives in
`.claude/settings.json` (template: `examples/claude-settings.json`); it was
re-enabled after the recursion guard landed. Kill switch for debugging:
`TREMULA_HOOKS_DISABLED=1` in the session environment.
