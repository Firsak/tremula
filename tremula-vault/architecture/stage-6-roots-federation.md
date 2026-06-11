---
depends_on:
- memory://tremula/modules/tremula-registry
- memory://tremula/modules/tremula-contracts
- memory://tremula/modules/tremula-distiller
- memory://tremula/modules/tremula-vault
scope: shared
source: distilled
type: architecture
---

# Stage 6: roots / federation

## Goal

Enable federated vault access across multiple projects via bridge vaults (roots). Projects coordinate on contracts (API boundaries, data schemas) by writing to a shared root vault, with per-side sections that prevent merge conflicts and make drift visible.

## Key design principles

**1. Bridge vaults (roots) connect member projects.** A root is a vault owned by none but visible to all its members. It appears in each member's mount set automatically; membership is declared via the registry. Non-members cannot access or write to roots—mount-set enforcement prevents escape.

**2. Contract notes have per-side sections.** Each endpoint/resource in a root vault has exactly one note; within that note, each member project owns a section (e.g., `## Provider (api)` / `## Consumer (webapp)`). A project **cannot** touch the other side's section by construction—`upsert_contract_section` replaces only its own, surgical merge. Drift is visible by design: when the provider updates to v2 and consumer still documents v1, both claims sit side by side.

**3. Federation rule is conditional on mounted roots.** The distiller includes a `FEDERATION` rule only when the project has member roots; standalone projects see zero prompt noise. When triggered, the rule teaches the LLM to emit contract ops (`{"action": "contract", "root", "title", "role", "content"}`); the apply_ops pipeline calls `upsert_contract_section` to write.

**4. Bootstrap integration — external-call drafting.** Stage 5's AST-driven external-call detection now writes drafts as consumer sections to roots (if the called service is a member). The provider side completes the same note later, naturally converging on one source of truth.

## Implementation

- **`tremula.contracts.upsert_contract_section`** — Surgically update contract sections; only the caller's role heading is rewritten.
- **Distiller federation rule** — `build_prompt` includes the rule only when roots are mounted; `apply_ops` dispatches `action: "contract"`.
- **`tremula root add` CLI** — Declare a new root; validates registry, requires ≥2 members, immediately visible in members' mount sets.
- **Mount-set enforcement** — Roots only appear in the mount set of members; non-members get MemoryURIError.

## Acceptance

- Both sides converge on one contract note (same URI, different sections) ✓
- Per-side sections, surgical merge (cannot touch other side) ✓
- Drift visible in note body (both claims present) ✓
- Non-member writes rejected (MemoryURIError) ✓
- Federation rule only when roots mounted ✓
