---
type: decision
scope: shared
depends_on: [memory://tremula/architecture/two-loops]
---

# Decision: which clients each loop supports

**Decision:** Treat the two loops as having different portability, and make that
explicit instead of assuming "Claude Code" everywhere.

- **Reactive loop (MCP server) — client-agnostic.** The FastMCP stdio server and
  its six tools speak the Model Context Protocol, so *any* MCP client (Claude
  Code, Codex, Gemini CLI, Cursor, a custom client) can call them. Nothing in
  `server.py`/`vault.py` depends on Claude Code.
- **Ambient loop (hooks) — host-specific.** Capture, SessionStart injection, and
  the auto-distiller are driven by Claude Code's hook lifecycle. Other hosts have
  their own (or no) event systems, so the ambient loop does **not** auto-run
  there. The `tremula hook <event>` CLI is generic, though: any host that can run
  a command on a lifecycle event can wire it the same way.
- **Distiller LLM — abstracted, independent of the client.** `ProviderConfig`
  decouples *who calls the tools* from *which model distills*. `claude-cli`
  (`claude -p`) is the zero-setup default but assumes the `claude` binary;
  `anthropic` (API key) or a local `base_url` (Ollama/llama.cpp) make
  distillation work for a user who never touches Claude Code.

**Why:** A Codex/Gemini user still gets the full reactive memory (search, graph,
write) — that is the portable core. They lose only the *automatic* capture and
injection until their host gains hook wiring, and they can still distill via the
API/local provider or by running `tremula distill` manually.

**Consequences:**
- Don't hard-depend on `claude` anywhere except the `claude-cli` provider.
- Document per-host hook setup (Claude Code: `examples/claude-settings.json`).
- A future "manual mode" — explicit `tremula capture`/`tremula distill` commands —
  would let any host drive the ambient loop without native hooks.
