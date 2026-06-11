---
depends_on:
- memory://tremula/modules/tremula-astmap
- memory://tremula/modules/tremula-config
- memory://tremula/modules/tremula-distiller
- memory://tremula/modules/tremula-index-md
- memory://tremula/modules/tremula-registry
- memory://tremula/modules/tremula-vault
scope: shared
source: distilled
type: module
---

# tremula.bootstrap

Generates initial vault from a codebase by scanning, building AST maps, and creating module/function summaries. All generated notes are protected and can be re-run idempotently.

## Public API
- `BootstrapPlan` — Plan state: repo_root, modules to summarize, import graph, key functions, external calls
- `plan_bootstrap(repo_root, max_modules=40, max_functions=10)` — Scan codebase and create deterministic bootstrap plan (no LLM, no writes)
- `run_bootstrap(vault, provider, plan, settings, registry=None, dry_run=False, judge_distilled=False)` — Execute plan: generate module/function/convention notes via LLM, apply distiller ops, rebuild index
