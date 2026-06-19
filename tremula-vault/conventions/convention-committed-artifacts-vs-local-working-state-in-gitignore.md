---
confirmation_count: 0
scope: shared
source: distilled
status: provisional
subject_paths: []
subject_symbols: []
type: convention
---

# Convention: committed artifacts vs. local working state in .gitignore

The repo commits **durable artifacts** (code, tests, vault notes, specs) and ignores **intermediate working output** and **per-user editor state**. Two boundaries that aren't obvious:

## `.omc/` — only durable `specs/` are committed
- **Committed:** durable specs in `.omc/specs/` (e.g. `deep-interview-tremula.md`, referenced from `CLAUDE.md`).
- **Ignored:** `.omc/plans/` and transient scratch specs (intermediate output, superseded), plus runtime state — `**/.omc/state/`, `**/.omc/sessions/`, `**/.omc/project-memory.json`. The `**/` prefix matches at any depth because tooling can drop a `.omc/` inside subdirs (e.g. cwd under `tremula-vault/`).

## Obsidian — vault notes committed, workspace config ignored
- **Committed:** the vault's markdown notes under `tremula-vault/`.
- **Ignored:** `.obsidian/` — per-user editor UI state (open panes, appearance, enabled plugins). It is per-user, not the repo's.

**Rule of thumb:** if it's a per-user/per-machine working artifact or a superseded intermediate, gitignore it; commit only the stable output. Related: [[conventions/convention-tremulaignore-skip-pattern-format]] (a separate, scanning-control ignore file) and [[conventions/examples-use-generic-placeholders-never-private-names]] (every committed file is a public artifact, so scan staged+untracked for private identifiers before committing).
