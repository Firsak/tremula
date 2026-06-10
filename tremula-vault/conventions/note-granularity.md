---
type: convention
scope: shared
---

# Note granularity: one note = one fact

Each note captures a single atomic fact or entity — a module, a key function,
a convention, or a decision. Notes are small on purpose: small notes link
cleanly, dedupe easily, and inject cheaply.

When a note outgrows one idea, split it (`split_note`): the original becomes an
index/oglavlenie pointing at the children. Per-note and per-injection size
limits (Stage 7) enforce this pressure toward consolidation.

Do **not** record ephemera: PR numbers, commit SHAs, transient TODOs. Record
durable knowledge: decisions, conventions, architecture, contracts.
