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
- [[architecture/stage-5-bootstrap-codebase-to-vault]] — Stage 5: Bootstrap — codebase to vault [architecture, distilled]
- [[architecture/stage-6-roots-federation]] — Stage 6: roots / federation [architecture, distilled]
- [[conventions/live-test-opt-in-via-marker]] — Live test opt-in via marker [convention, distilled]
- [[conventions/python-version-and-ruff-configuration]] — Python version and ruff configuration [convention, distilled]
- [[decisions/ast-driven-analysis-with-tree-sitter]] — AST-driven analysis with tree-sitter [decision, distilled]
- [[decisions/contract-surgical-section-merge]] — contract-surgical-section-merge [decision, distilled]
- [[decisions/decision-bootstrap-ast-driven-links-not-llm-inference]] — Decision: Bootstrap — AST-driven links, not LLM inference [decision, distilled]
- [[decisions/decision-bootstrap-brief-mode-zero-llm-stubs-with-async-enrichment]] — Decision: Bootstrap --brief mode — zero-LLM stubs with async enrichment [decision, distilled]
- [[decisions/decision-bootstrap-predictable-module-titles-for-idempotency]] — Decision: Bootstrap — predictable module titles for idempotency [decision, distilled]
- [[decisions/decision-bootstrap-reuses-distiller-apply-pipeline-for-protection]] — Decision: Bootstrap reuses distiller apply pipeline for protection [decision, distilled]
- [[decisions/decision-contract-sections-are-per-side-for-safety]] — Decision: Contract sections are per-side for safety [decision, distilled]
- [[decisions/decision-federation-rule-is-conditional-on-mounted-roots]] — Decision: Federation rule is conditional on mounted roots [decision, distilled]
- [[decisions/frontmatter-based-note-metadata]] — Frontmatter-based note metadata [decision, distilled]
- [[decisions/mcp-server-as-reactive-layer]] — MCP server as reactive layer [decision, distilled]
- [[functions/tremula-astmap-scan]] — tremula.astmap.scan [function, distilled]
- [[functions/tremula-capture-session-file]] — tremula.capture.session_file [function, distilled]
- [[functions/tremula-config-hooks-disabled]] — tremula.config.hooks_disabled [function, distilled]
- [[functions/tremula-config-index-path]] — tremula.config.index_path [function, distilled]
- [[functions/tremula-config-sessions-dir]] — tremula.config.sessions_dir [function, distilled]
- [[functions/tremula-contracts-upsert-contract-section]] — tremula.contracts.upsert_contract_section [function, distilled]
- [[functions/tremula-distiller-distill]] — tremula.distiller.distill [function, distilled]
- [[functions/tremula-index-md-sync-index-auto-section]] — tremula.index_md.sync_index_auto_section [function, distilled]
- [[functions/tremula-memory-uri-resolve]] — tremula.memory_uri.resolve [function, distilled]
- [[functions/tremula-note-load-note-in-vault]] — tremula.note.load_note_in_vault [function, distilled]
- [[functions/tremula-registry-resolve-session]] — tremula.registry.resolve_session [function, distilled]
- [[modules/tremula-astmap]] — tremula.astmap [module, distilled]
- [[modules/tremula-bootstrap]] — tremula.bootstrap [module, distilled]
- [[modules/tremula-capture]] — tremula.capture [module, distilled]
- [[modules/tremula-cli]] — tremula.cli [module, distilled]
- [[modules/tremula-config]] — tremula.config [module, distilled]
- [[modules/tremula-contracts]] — tremula.contracts [module, distilled]
- [[modules/tremula-distiller]] — tremula.distiller [module, distilled]
- [[modules/tremula-hooks]] — tremula.hooks [module, distilled]
- [[modules/tremula-index-md]] — tremula.index_md [module, distilled]
- [[modules/tremula-index]] — tremula.index [module, distilled]
- [[modules/tremula-injection]] — tremula.injection [module, distilled]
- [[modules/tremula-main]] — tremula.__main__ [module, distilled]
- [[modules/tremula-memory-uri]] — tremula.memory_uri [module, distilled]
- [[modules/tremula-note]] — tremula.note [module, distilled]
- [[modules/tremula-registry]] — tremula.registry [module, distilled]
- [[modules/tremula-server]] — tremula.server [module, distilled]
- [[modules/tremula-vault]] — tremula.vault [module, distilled]
- [[modules/tremula-workctx]] — tremula.workctx [module, distilled]
- [[modules/tremula]] — tremula [module, distilled]
<!-- /tremula:auto -->
