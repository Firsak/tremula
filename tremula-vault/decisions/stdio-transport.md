---
type: decision
scope: shared
---

# Decision: start on stdio; abstract the distiller provider

**Decision:** Make the server logic transport-independent (FastMCP gives this
for free) and **start on stdio**. Defer the HTTP/Streamable daemon to Stage 8.
Separately, abstract the distiller's LLM provider behind config
(`base_url + model + auth`).

**Why:** With stdio, project detection is free (one session = one child process,
cwd identifies the project) and there is no infrastructure to run. HTTP only
earns its keep once cold starts hurt or a shared warm daemon is wanted — not
before. Abstracting the provider means the default `claude -p` subscription path
(zero setup) can switch to the Haiku API or a local model (Ollama/llama.cpp)
with a one-line config change, no code rewrite.

**Consequences:** The MCP server (Stage 3) binds stdio first. The distiller
reads its provider from config; `ANTHROPIC_API_KEY` is only needed for the API
path, not the default `claude -p` path.
