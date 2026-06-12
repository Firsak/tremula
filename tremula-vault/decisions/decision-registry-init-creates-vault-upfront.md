---
depends_on:
- memory://tremula/modules/tremula-cli
- memory://tremula/modules/tremula-bootstrap
scope: backend
source: distilled
type: decision
---

# Decision: registry init creates vault upfront

**Problem:** `tremula registry init` (or `tremula init`) created a project record in the registry but deferred vault creation to bootstrap. Meanwhile, `tremula bootstrap` expected the vault directory to already exist, leading to a deadlock: bootstrap would fail if vault didn't exist, but init didn't create it.

**Decision:** `registry init` now creates the vault directory (`tremula-vault/`) and a starter `_index.md` file upfront. Bootstrap extends from there without preconditions.

The old behavior (record-only, no vault creation) is available via `--no-create` flag.

**Why:** Decouples project registration from bootstrap. A user can now run `tremula init` → `tremula bootstrap` → set up MCP server without circular failures. The vault directory is owned by init; bootstrap populates it.

**How to apply:** Document in README that `tremula init` is the vault setup step, not bootstrap. When adding projects to a registry, always run init first.
