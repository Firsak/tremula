---
type: decision
scope: shared
---

# Decision: vault at repo root, not .claude/memory/

**Decision:** The vault lives at `tremula-vault/` in the repository root and is
committed. It is **not** placed under `.claude/memory/`.

**Why:** `.claude/` and the `/memory` command are reserved by Claude Code (its
own auto-memory). Putting our vault there risks collisions with Claude Code's
built-in behavior. A top-level `tremula-vault/` also makes the memory a
first-class, reviewable repo artifact: it travels with the branch, the team
gets it via `git pull`, and changes are reviewed in PRs.

**Consequences:** Committed in-repo: `architecture/`, `modules/`,
`conventions/`, `decisions/`. Kept out of git: session distillates
(`~/.tremula/sessions/<project>/`), the SQLite index, and NDJSON logs — all
rebuildable cache. Markdown is the source of truth.
