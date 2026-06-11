# Deep Interview Spec: Tremula — Code-Memory MCP

## Metadata
- Interview ID: tremula-2026-06-10
- Rounds: 3
- Final Ambiguity Score: 19%
- Type: greenfield
- Generated: 2026-06-10
- Threshold: 20%
- Status: PASSED
- Source plan: `~/Downloads/tremula-architecture-plan.md` (Russian; project artifacts in English)

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.85 | 0.40 | 0.34 |
| Constraint Clarity | 0.78 | 0.30 | 0.234 |
| Success Criteria | 0.78 | 0.30 | 0.234 |
| **Total Clarity** | | | **0.808** |
| **Ambiguity** | | | **0.192** |

## Goal
Implement the **entire Tremula system** described in the architecture plan — a memory system for Claude Code that maintains an Obsidian-compatible markdown knowledge graph about a codebase, with **two loops**: a *reactive* MCP-server layer (tools the agent calls) and an *ambient* hooks layer (fires automatically on session lifecycle events, captures cheaply, distills with an LLM in the background, and injects memory at session start). Scope is **Stages 1–7** of the plan. All code, identifiers, comments, and docs in **English** (the plan is Russian; do not carry Russian into the codebase).

Terminology (keep these names):
- **ramet** — per-project vault (one "trunk")
- **genet** — the whole federation: registry + all ramets
- **roots** — bridge vaults linking ramets (shared root system / contracts)

Artifacts: PyPI package `tremula-mcp` · CLI `tremula` · `tremula-vault/` folder at repo root.

## Constraints
- **Language/stack (fixed by plan §9):** Python 3.12+ (provision via `uv` — system is 3.11.2); official `mcp` SDK (FastMCP); `python-frontmatter`; stdlib `sqlite3` + FTS5; links table in SQLite (no networkx); PyYAML + pydantic for the registry; `py-tree-sitter` + language packs (python, typescript, tsx) for bootstrap; tooling = `uv`, `ruff`, `pytest`; install path `uvx tremula-mcp`.
- **Transport:** start on **stdio** (project detected free via cwd). Logic is transport-independent (FastMCP gives this). HTTP daemon is **Stage 8 — out of scope**.
- **Retrieval:** **FTS5 only.** `sqlite-vec` semantic search is **Stage 8 — out of scope** (start with FTS, measure quality later).
- **Distiller LLM:** default = headless `claude -p` under the user's subscription (CLI confirmed present at `~/.local/bin/claude`). Provider must be **abstracted in config** (`base_url + model + auth`) so switching to Haiku API / local model is one config line. `ANTHROPIC_API_KEY` is currently UNSET — the API path is therefore unavailable until a key is added; the `claude -p` path does not need it.
- **Markdown is the source of truth; SQLite is a rebuildable cache.** Manual edits to vault files are picked up on next SessionStart.
- **Global addressing from day one:** `memory://project/path/note`, not local `[[title]]`.
- **Storage placement:** `tremula-vault/` at repo root (committed). Sessions/cache live outside git (`~/.tremula/sessions/<project>/`, SQLite index, NDJSON logs). **Never** use `.claude/memory/` (collides with reserved Claude Code names).
- **Hooks are on the hot path:** always `exit 0`, no LLM calls in the hook itself — must never slow a session. Include a fast hook-disable flag for self-debugging.
- **Mount-set access model:** server resolves `own ramet + all roots where project is a member` by cwd; everything outside the mount set is invisible to search/graph/injection.

## Non-Goals (explicitly out of scope)
- **Stage 8 entirely:** HTTP/Streamable daemon, `sqlite-vec` vectors, Rust indexer/watcher rewrite.
- Federating all projects with each other — only explicit `roots` pairs declared in the registry connect.
- Saving ephemera in notes (PR numbers, SHAs, transient TODOs) — distiller hygiene rules forbid it.
- Russian-language code/docs in the repo (the source plan stays as an external reference only).

## Status (updated 2026-06-11 — BUILD COMPLETE)
**All Stages 1–7 built, tested, and dogfooded.** 221 tests + 3 live opt-in,
all green. Beyond-spec work added along the way: distiller safety (provenance,
judged enrichment + no-loss backstop, `judge_distilled_updates`), distill
cadence (debounce + incremental offsets + per-session lock), fork-bomb guards,
memory:// path-traversal hardening, FTS5 crash-proofing, `_index.md`
auto-section, `bootstrap --brief` (zero-LLM) + focused targets, heat telemetry
with attic archiving, `.mcp.json` + hooks live (the vault wrote ~75% of its own
notes), public-ready Firsak history. Remaining: PyPI publish (deferred with
Stage 8: HTTP daemon, sqlite-vec, Rust watcher). Per-stage logs in
`stage-progress/` (untracked).

## Acceptance Criteria
Per-stage tests **and** dogfooding (Tremula self-hosts as its own first registry entry). "Done" = both gates pass.

- [x] **Stage 1 — Storage (ramet):** `tremula-vault/` scaffold (`_index.md`, `architecture/`, `modules/`, `functions/`, `conventions/`, `decisions/`); frontmatter schema (`type`, `scope`, typed wikilinks `depends_on`/`implements`/`decided_in`/`part_of`); `memory://` addressing convention; CLAUDE.md manual-mode instructions. Test: notes parse via `python-frontmatter`, memory:// URIs resolve.
- [x] **Stage 2 — Registry + mount set:** `~/.tremula/registry.yaml` (PyYAML + pydantic models for `projects` + `roots`); mount-set resolution by cwd. Test: pydantic validates registry; given a cwd, resolver returns own ramet + member roots only; out-of-set notes are excluded.
- [x] **Stage 3 — Reactive MCP server (FastMCP, stdio):** tools `write_note(title, content, links, type, scope)`, `read_note(uri)`, `get_context(topic, depth)`, `search(query, scope?)`, `link_notes(a, b, relation)`, `split_note(uri)`. SQLite FTS5 index over markdown (rebuildable). Test: pytest per tool; FTS returns ranked hits within mount set; index rebuilds from markdown.
- [x] **Stage 3 — Ambient hooks:** CLI `tremula hook <event>` for `PostToolUse`/`UserPromptSubmit`/`Stop` → append line to per-session NDJSON, always exit 0; hook-disable flag. SessionStart injection reads `_index.md` + N hot notes into context. Distiller: on `Stop`/`PreCompact`/`SessionEnd` a detached process runs `claude -p` over the session NDJSON and writes note updates to the ramet (+ root nodes), with hygiene rules in the prompt and a config-abstracted provider. Test: hook appends valid NDJSON & exits 0; injection emits `_index.md` + hot notes; distiller produces note diffs on a fixture NDJSON session.
- [x] **Stage 4 — Retrieval funnel:** `get_context(topic, depth)` does FTS seed + graph neighbors at depth 1–2, crossing vault boundaries via `memory://` within the mount set; `UserPromptSubmit` silently attaches 2–3 notes scoped by working context (recent file paths, git status, cwd) — not prompt words. Test: depth-bounded traversal returns expected neighbor set incl. cross-root contract consumers.
- [x] **Stage 5 — Bootstrap `/tremula-init`:** walk project (tree, configs, deps) → tree-sitter AST map (python/ts/tsx) → per-module subagent summaries into `modules/`+`functions/` → conventions/decisions pass → draft root nodes for external calls (if root declared) → generate `_index.md` + link the graph. Test: run on a sample repo produces a populated, internally-linked vault.
- [x] **Stage 6 — Roots/federation:** bridge vaults holding contracts (endpoints, shared types, event schemas); a root node referenced by both sides (implements / calls); distiller rule: external call or contract change → update the root node from this repo's side; contract drift visible in the note. Test: cross-repo contract node created and linked from both ramets; drift surfaces.
- [x] **Stage 7 — Consolidation/splitting:** turn counter triggers background revision every N turns (merge dupes, drop stale, split large notes); per-note + per-injection size limits force consolidation; `split_note` turns an oversized note's parent into an index. Test: oversized note splits with parent-as-index; dedupe merges; stale eviction runs.
- [x] **Cross-cutting — Dogfooding:** Tremula is the first `registry.yaml` entry; its own `tremula-vault/` exists from the first commit and is auto-maintained by the hooks/distiller as later stages come online; graph opens in Obsidian.
- [ ] **Packaging:** `uvx tremula-mcp` boots a working stdio server; `tremula` CLI runs. (Final PyPI/GitHub publish check is a Stage-8/open-question item — deferred.)

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| "Create an MCP" = just the FastMCP server | Asked what THIS build delivers | User: implement the **whole** project per the md, all of Stages 1–7 — not only the server |
| "All stages" includes optional Stage 8 | Where is the scope edge? | Stages 1–7; **defer Stage 8** (HTTP, sqlite-vec, Rust); FTS5-only |
| A memory system is hard to verify | What is the done-bar? | **Both** per-stage tests **and** self-hosting dogfood |
| Distiller LLM might be unavailable | Checked env directly | `claude -p` path works (CLI present); API path needs a key (unset) — provider stays config-abstracted |
| Doc's 4 open questions block progress | Decide vs ask | Pick sensible defaults, record each as a `decisions/` note (most map to deferred Stage 8) |
| Russian plan implies Russian code | User stated up front | Repo is **English**; the md stays an external reference |

## Technical Context
Greenfield. Working dir `~/programming_projects/tremula` is empty (only `.omc/`), no git yet. Toolchain verified: `claude`, `uv`, `git` present; Python 3.11.2 system (use `uv` for 3.12+); `ANTHROPIC_API_KEY` unset. The plan tags each subsystem with a `[Прототип]` (prototype) reference (claude-mem, Basic Memory, SuperBrain, Hermes, etc.) describing where the pattern already exists — use these as design references, not dependencies.

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| ramet | core domain | path, repo, scope, notes[] | part_of genet; addressed via memory:// |
| genet | core domain | registry, ramets[], roots[] | aggregates ramets + roots |
| root | core domain | members[], path, contract nodes | links 2+ ramets; holds contracts |
| registry | supporting | projects{}, roots{} (YAML) | defines genet topology; resolves mount set |
| note | core domain | title, type, scope, frontmatter, body, links | atomic fact; lives in ramet or root |
| distiller | external system | provider(base_url,model,auth), prompt | reads session NDJSON → writes notes |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1 | 6 | 6 | - | - | N/A |
| 2 | 6 | 0 | 0 | 6 | 100% |
| 3 | 6 | 0 | 0 | 6 | 100% |

Converged: the domain model from the plan was stable across all rounds — the interview clarified *scope and verification*, not *what the thing is*.

## Interview Transcript
<details>
<summary>Full Q&A (3 rounds)</summary>

### Round 1
**Q:** What is the target deliverable of THIS build — the scope to take to working code?
**A:** Not just an MCP — implement the whole project as written in the md file.
**Ambiguity:** 45% (Goal 0.70, Constraints 0.55, Criteria 0.35)

### Round 2
**Q:** How do we verify Tremula "works" — what's the done-bar?
**A:** Both: tests per stage AND dogfooding.
**Ambiguity:** 31% (Goal 0.72, Constraints 0.55, Criteria 0.78)

### Round 3
**Q:** Where's the boundary of "all stages" (Stage 8 optional; 4 open questions)?
**A:** Stages 1–7, defer Stage 8.
**Ambiguity:** 19% (Goal 0.85, Constraints 0.78, Criteria 0.78)

</details>
