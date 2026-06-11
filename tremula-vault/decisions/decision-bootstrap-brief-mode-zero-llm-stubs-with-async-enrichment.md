---
depends_on:
- memory://tremula/modules/tremula-bootstrap
- memory://tremula/modules/tremula-cli
scope: backend
source: distilled
type: decision
---

# Decision: Bootstrap --brief mode — zero-LLM stubs with async enrichment

**Problem:** On large codebases, full bootstrap (module + function + convention notes via LLM) can consume prohibitive tokens. Blocking bootstrap on LLM completion time is also slow.

**Decision:** `tremula bootstrap` now supports a three-tier workflow for big repos:

1. `tremula bootstrap --brief` (provider=None) — ZERO LLM. Generates stubs from docstrings + AST public symbols; exact `depends_on` links from import graph. Function and convention notes skipped. Returns instantly for project structure.

2. `tremula bootstrap <target> [...]` — User-chosen focus: file paths, directories, or dotted module names (e.g. `src/core/billing/`, `pkg.auth`) get full LLM treatment. Matched modules summarized; unmatched modules stay stubs. **Focused runs skip the project-wide conventions pass** (see [[decision-conventions-are-project-wide-not-per-module]]). Links span the full project graph; dangling links to unselected modules resolve later as the vault fills in.

3. Ambient enrichment — The distiller's enrichment loop updates stubs in place (same titles guarantee idempotency) as sessions touch each module. A later full `tremula bootstrap` (with provider) upgrades remaining stubs.

**Why:** Token-efficient initial structure for large repos; user controls where to invest LLM first; non-blocking workflow; enrichment spreads across sessions' distiller runs, hiding latency. Tested on real code: `tremula bootstrap src/tremula/contracts.py` enriched one module with accurate notes and correct deps.

**How to apply:** CLI bootstrap accepts optional positional targets. When set, `run_bootstrap` uses `only=<targets>` to filter the plan. When `provider=None` (--brief), skip LLM regardless of targets.
