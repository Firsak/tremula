---
scope: backend
source: distilled
type: architecture
---

# Stage 7: Consolidation / splitting (self-organization)

## Goal

Automate vault maintenance to keep notes organized and prevent duplication. This stage addresses real incidents: manual consolidation (deduplication of work-context notes, pruning of trivial conventions) happened twice. Stage 7 makes this deterministic and ambient.

## Key design principles

**1. Deterministic candidates, LLM only confirms.**  
Code discovers oversized notes, potential duplicates, and stale notes by measurable criteria (body size, title-token overlap, read frequency). The LLM only judges edge cases ("merge or not?", "still useful?"), never open-ended discovery. This prevents noise breeding noise.

**2. Distilled-only auto-apply.**  
Automated consolidation (splitting, merging, archiving) applies only to distilled notes. Manual notes are never touched—at most, suggestions appear in the distiller log. This preserves human authorship and prevents automated systems from corrupting hand-written knowledge.

**3. Archive, never delete.**  
Cold notes move to `attic/` (excluded from index, search, injection, and auto-section) instead of being deleted. Provides human-browsable recovery while keeping the live vault clean.

**4. Heat telemetry drives stale detection.**  
Each note tracks `reads` (count) and `last_read` (timestamp), incremented **only by user-facing reads** (MCP read_note tool, get_context injection, attachment logic). Machinery (distiller snapshots, revision pass queries) passes `track=False` so it never masquerades as usage. Heat survives note rewrites and full index rebuilds. Stale candidates are distilled notes with `reads==0`, zero inbound links, and age > threshold (14 days default).

## Implementation

**Heat telemetry** (`[[decision-heat-tracking-usage-metrics-for-stale-cleanup]]`):
- Index schema: `reads` (int) + `last_read` (unix timestamp)
- Incremented by: `VaultService.read_note(track=True)`, `get_context`, attachment
- Not incremented by: distiller existing-notes scans, revision pass queries, index rebuilds
- Persistence: heat carried across note upserts and full index rebuilds
- Conservative limit: deleting the cache DB resets telemetry; detector then stays quiet until usage re-accumulates

**Oversized split** (`[[tremula.revise]]`):
- Distilled notes with body > `max_note_chars` (default 8000) auto-split deterministically
- Parent note becomes an index (brief summary + child links)
- Content preserved end-to-end
- Manual oversized notes: logged as suggestion only, never auto-touched

**Duplicate merge:**
- Detects same-type distilled pairs sharing **discriminative** title tokens (tokens appearing in fewer notes overall, filtering out common package prefixes like `tremula.`)
- Head-token matching: a token counts as shared only if it heads both titles, preventing false positives (e.g., sibling functions `tremula.config.hooks_disabled` and `tremula.config.index_path` both have `config` but it's not HEAD in either)
- LLM judges whether merge is safe (validates content preservation against both bodies, 0.8 threshold)
- Winner (survivor): note with more inbound links or higher heat
- Merged body written to survivor's resolved file path
- Loser: archived to `attic/`
- Link rewiring: all notes referencing loser rewritten to point to survivor

**Stale archival:**
- Candidates: distilled notes with `reads == 0` + zero inbound links + age > 14 days
- Exempt types: `index` (self-referential), `contract` (shared across projects — one side's heat doesn't reflect the other's)
- Process: batched LLM confirmation before archival
- `attic/` notes: excluded from index refresh, search, injection, auto-section; recoverable via direct file browse

**Trigger mechanism:**
- Automatic: `revise()` called every Nth distillation run (N=5 configurable)
- On-demand: `tremula revise [--dry-run]` CLI

## Dogfooding discoveries

Three real bugs found and fixed while building the janitor:

1. **Merged content landed in wrong file** — title-to-slug mismatch in path resolution. Caught by regression suite.
2. **All `tremula.*` modules flagged as duplicates** — shared `tremula.` prefix treated as shared token. Fixed by filtering to **discriminative** tokens (those appearing in fewer notes). Caught by live dry-run on 60-note vault.
3. **Sibling functions flagged as duplicates** (e.g., `tremula.config.hooks_disabled` vs `tremula.config.index_path` sharing `config`) — fixed by head-token matching (token counts only if it's the title HEAD in both notes). Caught by next live dry-run.

After fixes: live dry-run correctly silent on clean vault; regression suite confirms real duplicates still caught.

## Scope and caveats

- **Duplicate detection is lexical** (word-overlap). Semantic duplicates await Stage 8 embeddings.
- **Stale threshold (14 days) empirically untested** — first real candidates appear in weeks. Conservative: stays in vault if uncertain.
- **Heat semantics:** heavily-consulted old notes survive; recently-written but never-used notes archive — trades recency for actual impact.
