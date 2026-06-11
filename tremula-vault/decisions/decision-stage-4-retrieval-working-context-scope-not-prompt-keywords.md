---
depends_on:
- memory://tremula/architecture/two-loops
- memory://tremula/architecture/mount-set
scope: backend
source: distilled
type: decision
---

# Decision: Stage 4 retrieval — working context scope, not prompt keywords

**Rule:** `UserPromptSubmit` attachment scope comes from working context (recent files, git status, cwd), never from prompt keyword analysis.

When the `UserPromptSubmit` hook attaches 2–3 notes via `get_context`, selection is scoped to observable system state: file paths and operations in the session NDJSON, git status changed files, working directory. The user's prompt text is never analyzed for retrieval keywords.

**Why:** Prompt keywords vary with user wording and hallucination; working context is ground truth (VCS state, file ops already captured in session). Original plan §5.3 and spec Stage 4 both mandate working context — that design decision is load-bearing and should not drift without explicit reason.

**How to apply:** `UserPromptSubmit` attachment reads (1) recent NDJSON for file operations and paths, (2) `git status` for changed files, (3) cwd path segments, then builds FTS seed from working context and expands via graph neighbors depth 1–2 within the mount set. Dedupe against SessionStart injection and previously attached notes via per-session URI sidecar. Prompt text is parsed for human context only; never tokenized for matching.

**Related:** [[architecture/two-loops]] (hook lifecycle), [[architecture/mount-set]] (retrieval scope boundary).
