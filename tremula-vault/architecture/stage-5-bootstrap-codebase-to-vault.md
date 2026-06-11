---
scope: shared
source: distilled
type: architecture
---

# Stage 5: Bootstrap — codebase to vault

## Goal

Generate an initial vault from a codebase: extract modules, functions, conventions, and decisions; build the link graph from import analysis; write to vault with full protections (reuse distiller pipeline). Acceptance: fixture repo produces a populated, internally-linked vault; idempotent re-run (updates existing notes, no duplicates); hand-written notes untouched.

## Key design principles

**1. AST-driven links, not LLM inference.** Module-to-module `depends_on` links come deterministically from the import graph (tree-sitter AST analysis), never from asking the LLM to infer them. Link quality is exact and reproducible; cannot hallucinate false dependencies.

**2. Reuse distiller apply pipeline for safety.** Bootstrap outputs vault operations (writes, links, splits) in the same format as the distiller and writes through the same `apply_ops` path. All safety mechanisms apply automatically: manual-note protection, judged enrichment (for distilled updates), dedup. Bootstrap is a different prompt set (AST + project analysis, not session NDJSON), feeding the existing safety machinery.

**3. Predictable module titles for idempotency.** Module note slug derives from the module's dotted import path (e.g., `src/tremula/vault.py` → `tremula.vault` → `modules/tremula-vault.md`). Re-running bootstrap uses the same slugs and updates existing notes instead of duplicating.

**4. _index.md integration already done.** The Stage 4 auto-section surfaces generated notes mechanically; curated content (above the markers) stays unchanged. No extra work needed.

## Pipeline outline

1. **Scan**: Deterministic walk of project files by language (py/ts/tsx), skip vendor/tests.
2. **AST extract**: Tree-sitter to extract functions, classes, exports, imports per file.
3. **Module notes**: LLM summarizes each module's purpose and public API as JSON; tolerant parsing (failed modules skip and log, never abort).
4. **Conventions/decisions**: LLM extracts project-specific conventions and design decisions.
5. **Link graph**: Build from import graph; emit `depends_on` links deterministically.
6. **Write and surface**: Write through distiller pipeline (safety free); auto-section surfaces all.

## Idempotency

Re-run is transparent: hits the same module slugs, updates existing notes, no spam. Status visible in auto-section and git diff.
