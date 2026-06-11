---
scope: backend
source: distilled
type: module
---

# tremula.revise

Self-organization janitor (Stage 7): auto-splits oversized distilled notes, merges detected duplicates with link rewiring, and archives cold notes. Applies deterministic candidate detection with LLM confirmation for judgment calls only.

## Public API

- `find_duplicate_candidates(vault: VaultService, threshold_tokens: int = 2) -> list[tuple[dict, dict]]` — Find same-type distilled note pairs sharing discriminative title tokens; returns pairs for LLM judge confirmation.
- `find_stale(vault: VaultService, index: Index, project: str, settings: Settings) -> list[str]` — Find distilled notes meeting stale criteria (reads==0, zero inbound links, older than stale_after_days) that are safe to archive.
- `revise(vault, mounts, index, project, provider, settings, dry_run=False) -> str` — Run one revision pass: split oversized notes, merge confirmed duplicates, archive confirmed stale ones; rewrite inbound links to merged survivors. Returns log summary. Triggered every Nth distill run (configurable) or via `tremula revise [--dry-run]` CLI.
- `archive_note(vault, mounts, uri)` — Move a note to `attic/` (excluded from index, search, injection); recoverable.
- `rewrite_inbound_links(vault, mounts, index, from_uri, to_uri)` — Rewrite all notes linking to `from_uri` so they point to `to_uri` instead.

## Design

**Deterministic candidates, LLM only confirms:** Measured criteria (body size, title-token overlap, read frequency) surface candidates; LLM judges edge cases only, never discovery.

**Duplicate merge:** Same-type distilled pairs sharing **discriminative** title tokens (filtered to avoid shared package prefixes). Head-token matching ensures sibling functions of the same module are not flagged as duplicates. Survivor is the better-anchored note (by inbound link count, then heat); merged body written to survivor's actual file; loser moved to `attic/`; all inbound links rewired.
