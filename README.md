# Tremula

> *Populus tremuloides* — the quaking aspen. The Pando colony is thousands of
> trunks sharing one root system: one organism. Tremula is the same shape for
> code memory — many project vaults, one federated knowledge graph.

**Tremula** is a code-memory MCP for Claude Code. It keeps an Obsidian-compatible
markdown note graph about a codebase and maintains it automatically through two
loops:

- **Reactive** — an MCP server exposing tools the agent calls on demand
  (`write_note`, `read_note`, `get_context`, `search`, `link_notes`, `split_note`).
- **Ambient** — Claude Code hooks that capture sessions cheaply, distill them
  with an LLM in the background, and inject relevant memory at session start.

### Concepts
| Term | Meaning |
|------|---------|
| `ramet` | one project's vault (a trunk) — `tremula-vault/` at repo root |
| `genet` | the whole federation: registry + all ramets |
| `roots` | bridge vaults linking ramets, holding shared contracts |

### Status
Built stage-by-stage. **Stage 1 (storage layer)** is in place: the vault
scaffold, note/frontmatter model, `memory://` addressing, and the `tremula` CLI
skeleton. Scope of the current effort is **Stages 1–7** (FTS5 retrieval; HTTP
daemon, `sqlite-vec`, and the Rust indexer are deferred Stage 8).

### Develop
```bash
uv sync --extra dev      # create env + install deps
uv run pytest            # run tests
uv run tremula vault     # list notes in this repo's vault
```
