---
scope: shared
source: distilled
type: decision
---

# contract-surgical-section-merge

Contract notes (in root vaults) store one note per contract, split into per-side sections (one for Provider, one for Consumer). Section merge is surgical by construction: a writer can only update its own role's section using `upsert_contract_section()`, never another side's. Sections coexist in the same markdown file, making contract drift visible when both sides disagree on the same endpoint or schema.
