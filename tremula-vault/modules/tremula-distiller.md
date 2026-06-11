---
depends_on:
- memory://tremula/modules/tremula-config
- memory://tremula/modules/tremula-memory-uri
- memory://tremula/modules/tremula-vault
scope: shared
source: distilled
type: module
---

# tremula.distiller

Transforms captured session events into durable markdown notes via an LLM. Abstracts the LLM provider (Claude CLI, Anthropic API, or custom) so the backend is pluggable. Runs detached from the hot path to avoid blocking vault operations.

## Public API
- `Provider (Protocol)` — Abstract interface for LLM backends; implement complete(prompt: str) -> str
- `ClaudeCliProvider(model=None, timeout=120)` — Default provider: shells out to `claude -p` with optional model override
- `AnthropicProvider(model, base_url, api_key)` — API-based provider using Anthropic SDK with specified model and endpoint
- `provider_from_config(cfg: ProviderConfig) -> Provider` — Factory: instantiate a provider from config (kind: claude-cli or anthropic)
- `build_prompt(events, existing_notes=None, budget=24000) -> str` — Construct LLM prompt from session events and optional existing notes, bounded by token budget
- `distill(events, existing_notes, provider, vault) -> dict` — Run the distiller: feed events to LLM, parse note operations, judge enrichments, apply to vault
- `judge_enrichment(original, proposed, provider) -> dict` — Judge whether a proposed note update preserves all original content while adding value
- `apply_ops(ops: list[dict], vault: VaultService) -> None` — Execute write and link operations on the vault; respects manual-note protection
