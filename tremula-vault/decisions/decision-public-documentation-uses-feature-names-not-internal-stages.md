---
scope: shared
source: distilled
type: decision
---

# Decision: Public documentation uses feature names, not internal stages

**Problem:** Tremula's development internally uses a 7-stage vocabulary (Stages 1–7). Early versions of README and pyproject.toml leaked this internal vocabulary to external users, creating confusion: what are "stages"? Why are they "deferred"? Is the project incomplete?

**Decision:** External documentation (README, pyproject.toml description, marketing) refers to stages **never**. Instead:
- **Current capabilities** by name: Obsidian-compatible vault, MCP server, focused bootstrap, auto-curation, contract management.
- **Roadmap items** by feature: PyPI release, sqlite-vec hybrid search, HTTP daemon, native file watcher.

**Why:** Stages document the project's own build history — useful internal metadata for the team. But external users care about what Tremula does and what's coming, not how we built it. Exposing stage vocabulary muddles the public narrative: it reads as project-management scaffolding, not a documented feature roadmap. The project should present as finished, self-hosting, and maintainable — which it is.

**How to apply:** Keep stage vocabulary in vault memory (architecture and decision notes) and agent-facing docs (CLAUDE.md). Use feature/capability names in README, API descriptions, and public communications. See [[architecture/stage-8-optional-enhancements-roadmap-and-trigger-conditions]] for the actual roadmap details.
