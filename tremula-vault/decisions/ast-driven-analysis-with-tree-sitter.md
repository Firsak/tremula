---
scope: shared
source: distilled
type: decision
---

# AST-driven analysis with tree-sitter

Tremula uses **tree-sitter** for syntax tree parsing of Python and TypeScript codebases (via `tree-sitter-python` and `tree-sitter-typescript` dependencies).

This enables precise, language-aware code extraction and linking in the AST map layer, avoiding regex-based parsing fragility.
