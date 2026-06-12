---
depends_on:
- memory://tremula/modules/tremula-astmap
- memory://tremula/modules/tremula-bootstrap
scope: shared
source: distilled
type: convention
---

# Convention: .tremulaignore skip-pattern format

Ignore policy moved from a git shell-out to an in-repository file: `.tremulaignore` (committed, per-project).

**Format:** One bare directory name per line (e.g. `node_modules`, `build`, `.venv`). No globs, no paths. A directory name matches at any depth in the project tree.

**Semantics:** Any directory whose basename (final component) matches an ignore pattern is pruned from the AST scan and bootstrap. This is the same depth-agnostic model as the hardcoded `SKIP_DIRS` baseline (`__pycache__`, `.pytest_cache`, etc.).

**Why:** Eliminates the git dependency for scanning control. Before: tremula had to shell out to `git ls-files` to determine what was trackable. Now: scanning is self-contained via `.tremulaignore` + hardcoded baseline. Makes the ignore behavior deterministic and independent of git state.

**How to apply:** Create `.tremulaignore` in the project root; add directories to skip (one per line). Both hardcoded baseline and `.tremulaignore` apply; `.tremulaignore` extends, not replaces.
