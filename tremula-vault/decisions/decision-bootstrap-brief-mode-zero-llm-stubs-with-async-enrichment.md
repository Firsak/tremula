---
depends_on:
- memory://tremula/decisions/decision-bootstrap-predictable-module-titles-for-idempotency
- memory://tremula/modules/tremula-bootstrap
- memory://tremula/modules/tremula-distiller
scope: backend
source: distilled
type: decision
---

# Decision: Bootstrap --brief mode — zero-LLM stubs with async enrichment

**Problem:** On large codebases, full bootstrap (module + function + convention notes via LLM) can consume prohibitive tokens. Blocking bootstrap on LLM completion time is also slow.

**Decision:** `tremula bootstrap --brief` (provider=None) skips LLM entirely and generates **stubs** using only zero-LLM signals:
- Module stubs: extracted docstrings + AST public symbols (functions, classes, exports).
- Exact depends_on links from import graph analysis.
- Function and convention notes skipped.

Enrichment happens **later, automatically**: the ambient distiller's enrichment loop updates the same notes (same titles guarantee idempotent updates, not duplication) as sessions touch each module. A subsequent full `bootstrap --full` (with provider) upgrades remaining stubs to rich summaries.

**Why:** Token-efficient initial structure for large repos; non-blocking interactive workflow; enrichment spreads across multiple sessions' distiller runs, hiding LLM latency behind ambient maintenance.

**How to apply:** Implement `--brief` flag in CLI. When set, `run_bootstrap` accepts `provider=None` and skips LLM-dependent passes. Use [[decision-bootstrap-predictable-module-titles-for-idempotency]] (same titles) so re-runs update stubs in place, and the existing ambient loop enriches them as documented in [[decision-distiller-safety]].
