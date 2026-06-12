---
scope: backend
source: distilled
type: module
---

# tremula.revise

Self-organization janitor (Stage 7): auto-splits oversized distilled notes, merges detected duplicates with link rewiring, and archives cold notes. Applies deterministic candidate detection with LLM confirmation for judgment calls only.

## Public API

- `find_duplicate_candidates(vault: VaultService, threshold_tokens: int = 2) -> list[tuple[dict, dict]]` — Find same-type distilled note pairs sharing discriminative title tokens; returns pairs for LLM judge confirmation. **Implementation uses document-frequency filtering**: tokens appearing in ≥30% of distilled note titles are excluded, preventing false positives on ubiquitous prefixes (e.g., `tremula.*` package names).
- `find_stale(vault: VaultService, index: Index, project: str, settings: Settings) -> list[str]` — Find distilled notes meeting stale criteria (reads==0, zero inbound links, older than stale_after_days) that are safe to archive.
- `revise(vault, mounts, index, project, provider, settings, dry_run=False) -> str` — Run one revision pass: split oversized notes, merge confirmed duplicates, archive confirmed stale ones; rewrite inbound links to merged survivors. Returns log summary. Triggered every Nth distill run (configurable) or via `tremula revise [--dry-run]` CLI.
- `archive_note(vault, mounts, uri)` — Move a note to `attic/` (excluded from index, search, injection); recoverable.
- `rewrite_inbound_links(vault, mounts, old_uri, new_uri)` — Rewrite all inbound references from `old_uri` to `new_uri` when merging duplicates.

## Critical implementation notes

**Merge write-path bug (fixed):** When writing merged content, always use the survivor's resolved path from `MemoryURI.resolve()`, never derive path from the merged body's H1 title. Title-derived slugs can diverge from canonical slugs, causing writes to land in wrong files.

**Stale archival exemptions:** Index and contract notes skip stale archival despite zero heat; shared notes and structural anchors have value independent of individual project heat.
