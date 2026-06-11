---
part_of:
- memory://tremula/architecture/stage-5-bootstrap-codebase-to-vault
scope: shared
source: distilled
type: decision
---

# Decision: Bootstrap — AST-driven links, not LLM inference

Module-to-module `depends_on` links come **deterministically from the import graph** (tree-sitter AST analysis), never from LLM inference or hallucination.

**Why:** LLM-inferred links hallucinate and cannot be trusted for correctness. Import graphs extracted by tree-sitter are ground truth — exact, reproducible, verifiable. Deterministic extraction ensures link quality and prevents false dependencies cluttering the vault.

**How to apply:** Extract imports/exports per file using tree-sitter; build the module dependency graph; emit `depends_on` links from each module's direct imports. Transitive traversal (depth-limited neighbors) is handled by the retrieval layer at query time, not by bootstrap link generation.
