---
depends_on:
- memory://tremula/modules/tremula-note
scope: shared
source: distilled
type: module
---

# tremula.index_md

Automatically maintains the unreviewed-notes section in `_index.md`, ensuring all newly created notes surface in the vault index. Regenerates the auto-section deterministically between HTML markers, listing notes not yet referenced in the manual part. Moving a note link from the auto-section to a curated heading is the human act of endorsing it.

## Public API
- `sync_index_auto_section(vault_root: str | Path, project: str) -> bool` — Regenerate the auto-section in _index.md; return True if the file changed
