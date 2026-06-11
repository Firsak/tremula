---
depends_on:
- memory://tremula/modules/tremula-capture
scope: shared
source: distilled
type: module
---

# tremula.workctx

Extracts working context (file paths and git changes) from session events and converts them into search terms for proactive note attachment in the retrieval funnel. Hot-path hook code: no LLM, bounded subprocess, fail-soft everywhere.

## Public API
- `extract_paths_from_events(events: list[dict], max_paths: int = 10) -> list[str]` — Most-recent-first distinct file paths mentioned in captured tool payloads.
- `git_changed_files(repo_root: str | Path, timeout: float = 0.5) -> list[str]` — Paths reported changed by git status --porcelain; empty list on any failure.
- `derive_terms(paths: list[str], max_terms: int = 12) -> list[str]` — Convert file paths into search terms: name stems and meaningful directory names.
- `working_context(session_path: str | Path | None, repo_root: str | Path | None, max_paths: int = 10) -> dict` — Assemble working context dict with paths and terms from session events and git status.
