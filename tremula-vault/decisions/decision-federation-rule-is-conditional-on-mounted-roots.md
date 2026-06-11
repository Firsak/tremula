---
depends_on:
- memory://tremula/modules/tremula-distiller
- memory://tremula/modules/tremula-registry
scope: shared
source: distilled
type: decision
---

# Decision: Federation rule is conditional on mounted roots

**Problem:** The distiller can emit a `FEDERATION` rule teaching the LLM about contract ops. But for standalone projects (those with no member roots), this rule is noise: it will never apply, and it consumes tokens in the prompt.

**Decision:** `build_prompt` checks the mount set for member roots. If roots exist, include the FEDERATION rule. If not, omit it entirely. The rule is thus conditional on registry state at distillation time.

**Why:** Standalone projects remain lean; their distiller prompt doesn't mention roots, contracts, or federation logic. Projects that join a root later will see the rule kick in automatically on next distillation, no code change.

**How to apply:** In `build_prompt`, derive member roots from the mount set (roots that list the current project as a member). Pass this list to the rule-building logic; only emit the FEDERATION rule if the list is non-empty.
