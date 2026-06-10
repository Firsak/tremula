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

## Conventions
- [[conventions/note-granularity]] — one note = one atomic fact
- [[conventions/frontmatter-schema]] — note types, scope, typed links
- [[conventions/memory-uri-addressing]] — global `memory://` addressing

## Decisions
- [[decisions/name-tremula]] — why the name Tremula
- [[decisions/stdio-transport]] — start on stdio; provider abstraction for the distiller
- [[decisions/vault-at-repo-root]] — vault lives at repo root, not `.claude/memory/`
- [[decisions/client-portability]] — reactive loop is client-agnostic; ambient loop is host-specific
- [[decisions/distiller-safety]] — recursion guard, source provenance, judged enrichment

## Terminology
- **ramet** — a single project's vault (one trunk)
- **genet** — the whole federation: registry + all ramets
- **roots** — bridge vaults linking ramets (shared contracts)
