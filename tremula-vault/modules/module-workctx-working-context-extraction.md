---
depends_on:
- memory://tremula/conventions/convention-tolerant-payload-extraction-for-hook-field-changes
- memory://tremula/decisions/decision-stage-4-retrieval-working-context-scope-not-prompt-keywords
part_of:
- memory://tremula/architecture/stage-4-proactive-memory-attachment-via-working-context-extraction
scope: backend
source: distilled
type: module
---

# Module: workctx — working-context extraction

Working-context extraction for Stage 4 proactive memory attachment. Derives searchable terms from observable system state (recent file operations, git status, cwd) rather than analyzing user prompts — per plan §5.3 and Stage 4 spec.

## Public API

```python
def extract_paths_from_events(events, max_count=10) -> list[str]:
    """Extract newest-first distinct file paths from captured session events.
    
    Recursive scan of event payloads for path-like strings (starts with `/`, `.`, `~`,
    contains `/` separators). Tolerant of hook schema drift: matches PATH_KEYS patterns
    (file_path, path, notebook_path, etc.) in any nested structure. Adapts to Claude Code
    updates without code changes.
    """

def git_changed_files(repo_root, timeout_s=0.5) -> list[str]:
    """Extract changed file paths from `git status --porcelain`.
    
    Timeout: 0.5s (fail-soft on slow repos). Handles renames (A → B counted as both).
    """

def derive_terms(paths: list[str]) -> set[str]:
    """Derive searchable FTS terms from file paths.
    
    Splits path components by snake_case/kebab-case; drops structural stopwords
    (src, tests, __pycache__, .git, etc.) that add noise to search scope.
    
    Example: `src/tremula/memory_uri.py` → {memory, uri}
    """

def working_context(session_path: str, repo_root: str) -> dict:
    """Extract working context for a session.
    
    Returns {paths, terms}: recent file operations and derived searchable terms.
    Used by `UserPromptSubmit` hook to scope proactive note attachment (2–3 notes).
    """
```

## Integration

Used by `injection.py:attach_notes` to:
1. Build FTS seed from working-context terms (not prompt keywords).
2. Expand via graph neighbors (depth 1–2) within the mount set.
3. Dedupe against SessionStart injection + previous attach via per-session URI sidecar.
4. Inject ≤3 notes, ≤1500 chars total, 400 chars per note (excerpt).

Scopedrules: working context only (recent files, git status, cwd), never prompt text — per decision [[decision-stage-4-retrieval-working-context-scope-not-prompt-keywords]].
