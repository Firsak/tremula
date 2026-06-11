---
depends_on:
- memory://tremula/modules/tremula-astmap
- memory://tremula/modules/tremula-note
- memory://tremula/decisions/decision-bootstrap-predictable-module-titles-for-idempotency
scope: backend
source: distilled
type: module
---

# tremula.bootstrap

Generates initial vault from a codebase by scanning, building AST maps, and creating module/function summaries. All generated notes are protected and can be re-run idempotently.

## Public API

- `plan_bootstrap(repo_root, max_modules=40, max_functions=10)` — Scan codebase and create deterministic bootstrap plan (no LLM, no writes)
- `run_bootstrap(vault, provider, plan, settings, registry=None, dry_run=False, judge_distilled=False)` — Execute plan: generate module/function/convention notes via LLM, apply distiller ops, rebuild index. `provider=None` allowed for `--brief` mode (zero-LLM stubs).

## Bootstrap modes

**Full bootstrap** (default): Calls LLM to generate rich module/function/convention summaries. `provider` required.

**Brief bootstrap** (`--brief` CLI flag): Zero-LLM mode: module stubs from docstrings + AST public symbols; import graph dependencies exact; function/convention passes skipped; `provider=None` allowed. Creates initial structure quickly for large repos. Stubs are idempotent (same titles) so re-runs update in place, and the ambient distiller enriches them as sessions touch each module.
