---
depends_on:
- memory://tremula/architecture/stage-6-roots-federation
- memory://tremula/modules/tremula-contracts
scope: shared
source: distilled
type: decision
---

# Decision: Contract sections are per-side for safety

**Problem:** In federated vaults, multiple projects coordinate on contracts. If one note holds *both* provider and consumer claims and both can be rewritten by an LLM, an LLM error in one project can corrupt the other's documented contract.

**Decision:** Each contract note has exactly one section per member project (`## Provider (api)` / `## Consumer (webapp)`). A project can only rewrite its own section; the other side's section is *structurally inaccessible*. The merge is surgical by construction, implemented in `upsert_contract_section`.

**Why:** Prevents corruption by construction, not by convention. No amount of prompt engineering can prevent an LLM hallucination from damaging the other side if both sections are writable. But if the write function *only touches its own section*, no hallucination can escape.

**Consequence — drift is visible:** When provider updates to v2 and consumer still documents v1, both claims sit side by side. This surfaces misalignment visually, making it easier for humans to notice and resolve.

**How to apply:** Implement `upsert_contract_section` to (1) load the note, (2) parse its sections by role, (3) replace only the caller's section, (4) rewrite. Validate mount-set membership; raise MemoryURIError if non-member.
