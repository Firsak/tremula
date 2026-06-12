---
depends_on:
- memory://tremula/decisions/decision-registry-init-creates-vault-upfront
scope: backend
source: distilled
type: function
---

# tremula.index_md.sync_index_auto_section

Regenerate the auto-section in `_index.md` with newly discovered notes; returns True if the file changed.

**Self-healing:** when `_index.md` is missing, the function creates it (scaffold heading `<project> — memory vault` plus empty auto-section markers) and populates it, instead of bailing out as a no-op. The function owns creating the file it maintains, so a hand-made or pre-0.1.3 vault — where `registry init` never wrote the index — gets a valid `_index.md` from the next sync. That sync runs inside bootstrap, the distiller, and the revision pass, so every caller self-heals. Still idempotent once the file exists: a no-change sync returns False.
