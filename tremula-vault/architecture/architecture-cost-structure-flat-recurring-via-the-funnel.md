---
depends_on:
- memory://tremula/architecture/stage-4-proactive-memory-attachment-via-working-context-extraction
- memory://tremula/decisions/decision-bootstrap-brief-mode-zero-llm-stubs-with-async-enrichment
scope: shared
source: distilled
type: architecture
---

# Architecture: Cost structure — flat recurring via the funnel

## Principle

The retrieval funnel design (Stage 4) ensures **all recurring costs stay flat regardless of vault size**. No vault-wide scans; every tool interaction is scoped to a fixed context window.

## Recurring costs (size-invariant)

**SessionStart injection:** Vault index + hot notes, hard-capped at 8,000 chars. A 10,000-note vault injects the same volume as a 50-note one. Funnel never loads everything.

**Per-prompt attachment:** Working-context-scoped note selection, hard-capped at 1,500 chars. Dedupe across session means intense attachment on first few prompts of a topic, then silent thereafter.

**Distiller background loop:** Fixed snapshot size (existing distilled notes capped at 40 notes) + fixed event budget (24k chars). Frequency is work cadence (debounced ≥10 min), not project size.

## Bootstrap: the one size-sensitive cost

Full bootstrap generates one note per module (one LLM call per module). Scales with project size. This is why `--brief` mode (zero-LLM stubs) and targeted enrichment exist: to unblock large-codebase adoption without prohibitive upfront cost.
