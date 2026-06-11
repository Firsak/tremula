---
type: index
scope: shared
---

# Tremula — Project Index

Entry point for Tremula's own memory vault (the `ramet`). Tremula is its own
first registry entry — this vault is maintained from the first commit and,
as later stages come online, auto-updated by the hooks/distiller loop.

> Tremula is a code-memory MCP for Claude Code: an Obsidian-compatible note
> graph about a codebase, with a **reactive** MCP-server layer and an
> **ambient** hooks layer that captures, distills, and injects memory
> automatically.

## Architecture
- [[architecture/mount-set]] — what a session can see (ramet + member roots)
- [[architecture/two-loops]] — reactive MCP server + ambient hooks
- [[architecture/stage-4-proactive-memory-attachment-via-working-context-extraction]] — the three-step retrieval funnel (distilled)

## Conventions
- [[conventions/note-granularity]] — one note = one atomic fact
- [[conventions/frontmatter-schema]] — note types, scope, typed links
- [[conventions/memory-uri-addressing]] — global `memory://` addressing
- [[conventions/convention-tolerant-payload-extraction-for-hook-field-changes]] — scan hook payloads tolerantly (distilled)

## Decisions
- [[decisions/name-tremula]] — why the name Tremula
- [[decisions/stdio-transport]] — start on stdio; provider abstraction for the distiller
- [[decisions/vault-at-repo-root]] — vault lives at repo root, not `.claude/memory/`
- [[decisions/client-portability]] — reactive loop is client-agnostic; ambient loop is host-specific
- [[decisions/distiller-safety]] — recursion guard, source provenance, judged enrichment
- [[decisions/distill-cadence]] — debounce, incremental offsets, per-session lock
- [[decisions/decision-index-freshness-via-mtime-revalidation-not-dirty-flags]] — pull-based cache consistency (distilled)
- [[decisions/decision-sessionstart-resets-injection-sidecar-after-compaction]] — compact blind-spot fix (distilled)
- [[decisions/decision-stage-4-retrieval-working-context-scope-not-prompt-keywords]] — attach scope per plan §5.3 (distilled)

## Terminology
- **ramet** — a single project's vault (one trunk)
- **genet** — the whole federation: registry + all ramets
- **roots** — bridge vaults linking ramets (shared contracts)

<!-- tremula:auto -->
## Unreviewed notes (auto-listed; move a link up to endorse it)
- [[modules/module-index-md-index-md-auto-section-sync]] — Module: index_md — _index.md auto-section sync [module, distilled]
- [[modules/module-workctx-working-context-extraction]] — Module: workctx — working-context extraction [module, distilled]
<!-- /tremula:auto -->
