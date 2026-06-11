---
depends_on:
- memory://tremula/decisions/distiller-safety
part_of:
- memory://tremula/architecture/stage-5-bootstrap-codebase-to-vault
scope: shared
source: distilled
type: decision
---

# Decision: Bootstrap reuses distiller apply pipeline for protection

Bootstrap outputs vault operations (note writes, links, splits) in the same format as the distiller and writes through the same `apply_ops` pipeline. All protections apply automatically: manual-note guards, judged enrichment, dedup.

**Why:** Avoid reimplementing protection logic. Consistency across all vault writes (distiller, bootstrap, future agents). Zero risk of bootstrap clobbering hand-written notes or duplicating distilled updates.

**How to apply:** Format bootstrap output as ops (list of write/link/split actions with source="distilled", protect=True). Pass through the existing `apply_ops` path. Judge and protection rules apply automatically.
