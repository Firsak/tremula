---
depends_on:
- memory://tremula/conventions/frontmatter-schema
scope: shared
source: distilled
type: module
---

# Module: index_md — _index.md auto-section sync

Auto-section synchronization to surface new and distilled notes in `_index.md` without an LLM.

## Purpose

Every vault's `_index.md` must list newcomers (distilled notes, manual adds, vault edits) automatically while preserving human curation. This module deterministically surfaces unlinked notes in a machine-owned section.

## Public API

```python
def sync_index_auto_section(vault_dir: str | Path, project_key: str) -> bool:
    """Sync machine-owned section of _index.md to list unlinked notes.
    
    Scans vault for all notes, lists those NOT referenced in human-curated part
    (both [[wikilink]] and memory:// URIs count as linked). Returns True if changed;
    writes only on diff. Tolerant of missing _index.md (no-op).
    """

AUTO_BEGIN = '<!-- tremula:auto -->'    # auto-section markers
AUTO_END = '<!-- /tremula:auto -->'
```

## Design

_index.md splits into two regions:

1. **Human-curated part** (above markers): preserved byte-for-byte, never modified.
2. **Machine-owned auto-section** (between markers): lists every vault note **not referenced** in curated part. Both `[[path/note]]` wikilinks and global `memory://project/path/note` URIs count as "linked."

Sync behavior:
- Deterministic: sorted by path; reads note title and type from frontmatter.
- Idempotent: writes only when content changes.
- Tolerant: works with any _index.md structure; only markers matter.

## Endorsement workflow

To curate a note: move its link from the auto-section up into a proper heading in the human-curated part. On the next sync, it disappears from the auto-list because it's now "referenced." The note itself is unchanged; only index position changes.

## Triggers

- `SessionStart`: before cache rebuild + injection (injected index already lists newcomers)
- After `run_distill`: every time distiller applies note operations

## Tolerances

- Missing `_index.md`: sync is a no-op
- Any vault layout: only markers and frontmatter parsing matter
- Note structure: reads title and type; tolerates missing fields

## Consequence

Distilled notes become visible in the index within seconds of being written, without an LLM touching the index. Human oversight: review auto-section, move links up to endorse, next sync respects it.
