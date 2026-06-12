---
depends_on:
- memory://tremula/modules/tremula-config
scope: backend
source: distilled
type: decision
---

# Decision: Agent-agnostic distiller/bootstrap provider — no vendor default

**Problem:** The LLM backend for distiller + bootstrap was effectively Claude-locked: default `kind=claude-cli`, and `provider_from_config` only handled `claude-cli` + `anthropic`. This contradicts Tremula's goal of being CLI-agent-agnostic — a gemini/codex user got a Claude-centric default and `describe()` output.

**Decision:** The provider is universal and picks no vendor for you.

- **`CliProvider`** runs ANY one-shot agent CLI. A `{prompt}` token in the command => prompt passed as an arg; without it, prompt is piped on stdin. `{model}` token => the `model` field.
- **Default `kind=auto`**: auto-detect an agent CLI on PATH (claude/gemini/codex via `AGENT_PRESETS`) and use it — no API key, no vendor lock-in.
  - Multiple agent CLIs installed => errors, asks you to pin `provider.agent` (never silently prefers one).
  - No agent CLI but an API key present => Anthropic API.
- **`kind=cli`** (explicit `command` or named agent preset) and **`kind=anthropic`** (SDK) remain. **`kind=claude-cli`** kept as a back-compat alias.
- **`ProviderConfig.describe()`** states backend + exact auth; the default reads "no provider lock-in; no API key". Bootstrap plan output prints it plus a `--brief` nudge when a run exceeds 12 LLM calls, so agents stop guessing about the API key.
- `ClaudeCliProvider` missing-binary now raises a clear, actionable error instead of `FileNotFound`.

**Why:** Honors the agent-agnostic goal; standalone/no-key users still get distillation via whatever agent CLI they have.

**Caveat:** `gemini`/`codex` preset flags (`gemini -p {prompt}`, `codex exec {prompt}`) are best-effort and unverified against live CLIs; only `claude` is confirmed. If a preset's flags are wrong, `kind=cli` + explicit `command` always works.

**How to apply:** Don't reintroduce a vendor default. New agents go in `AGENT_PRESETS`. Document `provider.agent` (to disambiguate when several CLIs exist) and the `{prompt}`/`{model}` token contract in README's "Choosing the model provider" section.
