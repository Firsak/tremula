---
confirmation_count: 0
depends_on:
- memory://tremula/decisions/decision-public-documentation-uses-feature-names-not-internal-stages
scope: shared
source: distilled
status: provisional
subject_paths: []
subject_symbols: []
type: convention
---

# Convention: commit messages and PR descriptions are public artifacts — no internal process vocabulary

Tremula is public from the first commit (GitHub + PyPI). **Commit messages and PR descriptions are themselves public artifacts** — permanent in git history, visible to anyone reading the repo. They are not a private dev log.

**Rule:** keep them about *the change* — what changed and why, framed for an outside reader of the repo. Do **not** leak internal development-process or tooling vocabulary: AI/agent orchestration role names, internal pipeline or workflow names, scratch artifact paths, or any other scaffolding that is meaningless outside this workspace. A PR section describing *how the work was produced* (the build pipeline) rather than *what changed* is exactly the kind of unrelated content to omit.

**Why:** generalizes the README/packaging rule (public docs use feature names, never the internal 7-stage vocabulary — see [[decisions/decision-public-documentation-uses-feature-names-not-internal-stages]]) from package docs to git artifacts. Same principle as keeping private names out of committed files (see [[conventions/examples-use-generic-placeholders-never-private-names]]): once pushed it persists in history and can only be scrubbed by a rewrite + force-push.

**How to apply:** before committing/opening a PR on a public repo, reread the message as an outsider would — strip any section that documents *how the work was produced* rather than *what the change is*. Match the repo's existing commit/PR conventions rather than importing tool-default boilerplate.
