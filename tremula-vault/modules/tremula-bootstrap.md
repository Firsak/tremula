---
depends_on:
- memory://tremula/modules/tremula-cli
- memory://tremula/decisions/decision-bootstrap-brief-mode-zero-llm-stubs-with-async-enrichment
scope: backend
source: distilled
type: module
---

# tremula.bootstrap

Generates initial vault from a codebase by scanning, building AST maps, and creating module/function summaries. All generated notes are protected and can be re-run idempotently.

## Public API

- `plan_bootstrap(repo_root, max_modules=40, max_functions=10, only=None)` — Scan codebase and create deterministic bootstrap plan (no LLM, no writes). `only=<list of targets>` filters to matched modules (file paths, directories, or dotted module names); external-call detection and reference counting span the full project for accuracy.
- `run_bootstrap(vault, provider, plan, settings, registry=None, dry_run=False, judge_distilled=False)` — Execute plan: generate module/function/convention notes via LLM, apply distiller ops, rebuild index. `provider=None` allowed for `--brief` mode (zero-LLM stubs). When `plan.only` is set (focused run), conventions pass is skipped.

## Bootstrap modes

**Full bootstrap** (default): Calls LLM to generate rich module/function/convention summaries for the entire project. `provider` required.

**Brief bootstrap** (`--brief` CLI flag): Zero-LLM mode: module stubs from docstrings + AST public symbols; import graph dependencies exact; function/convention passes skipped; `provider=None` allowed. Creates initial structure instantly for large repos. Stubs are idempotent (same titles) so re-runs update in place, and the ambient distiller enriches them as sessions touch each module.

**Focused bootstrap** (`bootstrap <target> [...]` CLI syntax): User-chosen targets (file paths, directories, or dotted module names) get full LLM treatment. Matched modules summarized; unmatched modules remain stubs. Links span the full project graph; dangling links to unselected modules resolve later. **Conventions pass is skipped** — conventions are project-wide facts, not per-module; re-deriving them from a fragment over-generates noise and duplicates. `provider` required.
