---
depends_on:
- memory://tremula/decisions/decision-bootstrap-ast-driven-links-not-llm-inference
part_of:
- memory://tremula/architecture/stage-5-bootstrap-codebase-to-vault
scope: backend
source: distilled
type: module
---

# tremula.astmap

Deterministic AST-driven extraction of source code structure using tree-sitter (v0.25). Recovers modules, functions, classes, exports, and import graphs without LLM or hallucination. Foundation for the bootstrap stage.

## Public API

- `scan(repo_root: Path, exclude_dirs: set[str] | None = None) -> list[Path]` — Recursively find source files, skipping junk directories (node_modules, .venv, .git, vault, __pycache__, test directories).
- `map_file(path: Path) -> FileMap` — Extract symbols (functions, classes, constants) with export status, plus raw imports. Handles decorated definitions; Python uses underscore convention for privacy, TypeScript uses `export` keyword.
- `dotted_name(file_path: Path, repo_root: Path) -> str` — Compute project-unique module name from file path: `src/tremula/vault.py` → `tremula.vault`, `__init__.py` → enclosing package. This name becomes the note title for bootstrap, enabling idempotency (same module always produces same-titled note, so re-runs update in place instead of duplicating).
- `resolve_import(import_spec: str, from_file: Path, repo_root: Path) -> Path | None` — Resolve relative or absolute imports to project file paths.
- `import_graph(files: list[Path], repo_root: Path) -> dict[str, set[str]]` — Build module dependency graph: `{module_dotted_name: {direct_dependencies}}`. Fully deterministic from imports, never LLM-inferred.

## Languages supported

Python 3, TypeScript, TSX (via tree-sitter grammar plugins).
