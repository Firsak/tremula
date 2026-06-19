---
depends_on:
- memory://tremula/architecture/architecture-memory-is-project-scoped-not-branch-aware-single-trunk-assumption
scope: backend
source: distilled
type: decision
---

# Decision: Branch-aware memory scoping via lifecycle accrual, not branch identity

**Problem:** Tremula has no branch/worktree dimension, so a note distilled while working a feature branch is injected into sessions on another branch where that code doesn't exist yet — cross-branch memory pollution. See [[architecture/architecture-memory-is-project-scoped-not-branch-aware-single-trunk-assumption]].

**Rejected — branch identity.** Tagging notes with the branch they were written on and filtering by current branch is the literal fix but fragile: branch rename/delete/reuse, detached HEAD, colleague branches. It also smuggles VCS merge semantics into what is a memory DB, not a versioning tool. The real question is not "what branch was this note born on?" but "is the code this note describes in front of me right now, and is this fact settled or in-flight?" — both answerable without branch identity.

**Chosen axis — lifecycle status + working-tree grounding, ratified by accrual.** A note is born `provisional`. Each distiller pass re-checks it; every time the subject code is observed present in the working tree, a confirmation counter increments (blockchain-style accrual). After several confirmations the note crosses a threshold and becomes `ratified`/trusted. Degrades gracefully with no git.

**Code binding — subject paths + AST symbols.** At birth the distiller stamps `subject_paths` (from the session's changed files, via `workctx.git_changed_files`) AND the symbols the note names (functions/classes). A confirmation = those paths exist AND the symbols still resolve in the current tree's AST (`astmap`, tree-sitter). Robust to noise; catches half-deleted/stubbed code that bare path-existence would miss.

**Inject rule — suppress absent, rank by trust.** Provisional + subject code NOT in the working tree = never injected, on BOTH surfaces: `build_injection` (SessionStart hot-notes-by-mtime — the worst leak) and `build_attachment` (UserPromptSubmit FTS). Ratified notes are always eligible. Eligible notes are ranked by confirmation count, so accrued trust also shapes ordering.

**Final parameters (as implemented).** Threshold to ratify defaults to 3 (`Settings.confirmation_threshold`); the counter is **monotonic** — code absent (incl. a plain branch switch) only suppresses injection for that session, never lowers trust. Confirmation runs in the **background distiller** (`_confirm_notes`, bounded by `confirmation_batch_size=30`), never on the inject hot path; the inject gate reads `status`/`subject_paths` straight off the index/`SearchHit` (zero extra queries). **Suppression is injection-scope only** — withheld notes stay fully searchable via the MCP `search`/`get_context`/`read_note` tools. Deletion or trust-lowering happens **only** via the explicit `tremula verify` command (`--prune`/`--lower`/`--ratify`), run when the user declares the code state canonical. Master rollback toggle: `lifecycle_enabled`. Existing notes are grandfathered as `ratified` (defaults-are-the-migration, no bulk rewrite); manual notes are born `ratified` and the confirmation pass never touches them.

**Status:** implemented on branch `feature/branch-aware-memory-scoping` (note.py, index.py, vault.py, config.py, injection.py, hooks.py, distiller.py, astmap.py, cli.py) with 22 tests in `tests/test_lifecycle.py`. Reuses existing machinery (`astmap.py` tree-sitter scan, `workctx.git_changed_files`, the note frontmatter `source` field). The distiller still rarely emits typed `part_of`/`implements` links, so binding relies on stamped paths+symbols rather than those links.
