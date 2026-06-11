---
part_of:
- memory://tremula/architecture/stage-5-bootstrap-codebase-to-vault
scope: shared
source: distilled
type: decision
---

# Decision: Bootstrap — predictable module titles for idempotency

Module note slug = dotted import path of the module. E.g., `src/tremula/vault.py` → `tremula.vault` → note title `tremula.vault` → file `modules/tremula-vault.md`. Re-running bootstrap uses the same slugs and updates (rather than duplicates) existing notes.

**Why:** Idempotency without explicit tracking or state. A re-run is transparent to the user — they see updates to existing notes, not spam of new notes. Bootstrap can be re-run safely anytime the codebase changes.

**How to apply:** For each module, compute its dotted import path (language-agnostic: Python modules as `a.b.c`, TS/TSX as `src/dir/file`). Use this as the note title and slug. On re-run, exact title match (via `write_note`) triggers update instead of create.
