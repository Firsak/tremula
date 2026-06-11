---
depends_on:
- memory://tremula/decisions/decision-bootstrap-brief-mode-zero-llm-stubs-with-async-enrichment
scope: backend
source: distilled
type: decision
---

# Decision: Conventions are project-wide, not per-module

**Problem:** Live dogfooding of focused bootstrap (enriching one module at a time) exposed a real flaw: when running `tremula bootstrap src/tremula/contracts.py`, the convention-generation pass re-derived project-wide conventions from one module's isolated perspective. Result: 5 notes from one file, including a duplicate of the hand-written `[[conventions/frontmatter-schema]]` convention, plus trivial noise ("role-enumeration" as a convention).

This is unsurprising: conventions describe the whole project, not individual modules. Re-deriving them from a fragment guarantees over-generation and hallucination.

**Decision:** Focused bootstrap runs **skip the project-wide conventions pass entirely**. Conventions only update via full `tremula bootstrap` (no targets) or ambient distiller enrichment of the full session context.

**Why:** Prevents spurious duplication and noise. Conventions are project-wide facts, not module-local facts; a one-module view cannot faithfully re-derive them. Dogfooding immediately validated this (noise was deleted, the one genuine decision `[[decisions/contract-surgical-section-merge]]` was kept).

**How to apply:** In `run_bootstrap`, when `only=<targets>` is set, omit the conventions pass from the plan.
