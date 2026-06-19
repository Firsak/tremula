---
depends_on:
- memory://tremula/architecture/stage-6-roots-federation
- memory://tremula/decisions/decision-contract-sections-are-per-side-for-safety
- memory://tremula/decisions/decision-federation-rule-is-conditional-on-mounted-roots
- memory://tremula/modules/tremula-contracts
scope: shared
source: distilled
type: architecture
---

# Architecture: Root vaults are born empty, enriched by member distillers

`tremula root add` creates an empty bridge vault. The root is never authored as a whole; it fills incrementally as **each member project's own distiller** writes contract sections into it. No central editor of a root exists — only per-side surgical upserts.

## Enrichment lifecycle

1. **Trigger — conditional federation rule.** When a root is mounted, the member's distiller `build_prompt` adds a `FEDERATION` rule teaching the LLM to emit a contract op (`{action: "contract", root, title, role: provider|consumer, content}`). Standalone projects omit the rule entirely. See [[decisions/decision-federation-rule-is-conditional-on-mounted-roots]].
2. **Write — surgical per-side merge.** `apply_ops` dispatches `action: "contract"` to `upsert_contract_section(vault, root_key, title, project, role, content)`. One note per endpoint/resource; each member owns exactly one section (`## Provider (api)` / `## Consumer (webapp)`); a write touches only its own role heading. See [[decisions/decision-contract-sections-are-per-side-for-safety]] and [[modules/tremula-contracts]].
3. **Convergence.** Both members write the *same* note URI in *different* sections. Source of truth is one note with two voices; drift (provider v2 next to consumer v1) sits side by side and is visible by design.

## Enrichment paths

- **Ambient (primary):** normal session work is distilled; the distiller emits a contract section for whichever side it observes.
- **Bootstrap drafting:** AST external-call detection (Stage 5) can spot a call from one member to another member's service and seed a consumer-side draft, with the provider completing the same note later.

Net: enrichment = members independently appending their own contract sections over time, never editing the root as a whole.
