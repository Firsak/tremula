---
depends_on:
- memory://tremula/decisions/decision-stage-4-retrieval-working-context-scope-not-prompt-keywords
scope: backend
source: distilled
type: architecture
---

# Stage 4: Proactive memory attachment via working-context extraction

## The three-step retrieval funnel

Memory reaches context in three waves, each step different latency/scope:

1. **SessionStart (Stage 3)**: Inject `_index.md` only — minimal, always visible, zero decision.
2. **User request `get_context` (Stage 3)**: FTS seed + graph neighbors (depth 1–2) within mount set — interactive, agent-driven, full search.
3. **UserPromptSubmit proactive attach (Stage 4)**: On each user prompt, silently discover 2–3 relevant notes scoped by working context — zero latency cost, fail-silent, no user decision.

## Design principle: working context, not prompt keywords

Proactive attachment is scoped by observable system state (recent file operations, git status, cwd), not by NLP on user prompts. This principle is chosen for ground truth: VCS state is verifiable; prompt text is noisy and varies with wording.

## Working-context sources

1. **NDJSON session log**: Recent file operations and paths from `PostToolUse` events (already captured in Stage 1; ~200-event window).
2. **git status**: Changed files in the working tree (`git status --porcelain`, 0.5s timeout).
3. **cwd**: Current working directory and its parent segments.

From these, derive search terms: filename stems and parent directory names, minus structural stopwords (`src`, `tests`, `lib`, etc.). Keep ~10 most recent distinct terms.

## Attachment mechanism

- **Search**: use OR-join semantics on working-context terms. Any term can match; rank by relevance.
- **Dedupe**: per-session sidecar records all previously-injected URIs. Never re-inject the same note across SessionStart + multiple UserPromptSubmit cycles.
- **Compact**: attach as a labeled block (≤3 notes, ≤1500 chars total). "Possibly relevant memory:" prefix; show titles + URI + ~400-char excerpt, not full text.
- **Fail-silent**: no matches, all-deduped, or empty working context → print nothing. Proactive attachment must never block or surprise.

## Implementation structure

- **New `workctx.py` module**: extract working-context terms from NDJSON + git + cwd.
- **`Index.search_any(terms)` method**: OR-ranked search to complement AND-ranked `search`.
- **Extend `injection.py`**: per-session sidecar tracking (`.injected.json`), `build_attachment` method to construct compact blocks.
- **SessionStart refactor**: `build_injection` returns injected URIs so sidecar records them.
