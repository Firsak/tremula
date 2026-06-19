---
depends_on:
- memory://tremula/architecture/mount-set
scope: backend
source: distilled
type: architecture
---

# Architecture: Memory is project-scoped, not branch-aware (single-trunk assumption)

> **Resolved in 0.1.6.** This note describes the *prior* limitation and where it lived; it is now addressed by note lifecycle + working-tree grounding. See [[decisions/decision-branch-aware-memory-scoping-via-lifecycle-accrual-not-branch-identity]]. Kept as the problem record the fix refers back to.

Tremula *originally* had **no branch / worktree / code-state dimension anywhere** in the pipeline. Capture, retrieval, and registry all collapsed to a single project key, so notes distilled while working on one feature branch were injected into sessions running on a different branch where that code doesn't exist yet — cross-branch memory pollution. This was a design-level property (single-trunk assumption), not a bug in one function — which is why the fix added a dimension rather than patching one line.

## Where the assumption lives

**Capture / provenance** — `capture.append_event` stores `{ts, event, payload}` and preserves all payload keys recursively (clipping only long strings). Claude Code's hook payload *does* carry `gitBranch`, so it survives into the session NDJSON, but nothing reads it. `distiller.apply_ops` → `vault.write_note(..., source="distilled")` has params for type/scope/links/source/protect but **no branch/commit/path field**. `note.NoteFrontmatter` = {type, scope∈{backend,frontend,shared}, source∈{manual,distilled}, links} — unknown keys are kept in `extra`, but no provenance key is ever stamped.

**Retrieval / injection** — `injection.build_injection` (SessionStart) selects "hot" notes via `index.all_notes()` = `SELECT * FROM notes ORDER BY mtime DESC` with no predicate; feature-branch notes have the freshest mtime and rank first on a new session opened on main. `injection.build_attachment` calls `index.search_any(terms)` with **no scope argument**. The index layer already implements a scope filter (`search`/`search_any` conditionally append `AND n.scope = ?`; `scope` column + `idx_notes_scope` populated on every upsert) — it is simply never activated by any ambient injection callsite. The only git signal at retrieval time is `workctx.git_changed_files()` = `git status --porcelain` (dirty paths only); no `git branch`/`rev-parse` call exists.

**Registry** — `find_project_by_cwd` resolves by cwd and intentionally collapses git checkouts to the innermost project; `mount_set` = one ramet + roots. Git is acknowledged at this layer but reduced to project identity, never branch.

## Fix locus (as implemented in 0.1.6)

Both levers below were taken. **Provenance at capture/distill time:** the distiller stamps a durable subject binding — `subject_paths` (touched files) + `subject_symbols` (AST symbols) — not the fragile branch name (renamed, deleted post-merge, reused, detached HEAD). **Retrieval-time filter:** `build_injection` / `build_attachment` now gate on whether that subject code is present in the working tree (`index.eligible_notes` / `injection._is_eligible`), and rank by an accrued confirmation count. No branch concept is introduced. Full design + parameters in [[decisions/decision-branch-aware-memory-scoping-via-lifecycle-accrual-not-branch-identity]].
