---
depends_on:
- memory://tremula/modules/tremula-contracts
- memory://tremula/modules/tremula-vault
scope: shared
source: distilled
type: function
---

# tremula.contracts.upsert_contract_section

Create or surgically update a contract section in a shared root vault.

**Signature:**
```python
def upsert_contract_section(vault: VaultService, root_key: str, title: str,
                            project: str, role: str, content: str) -> str
```

**Behavior:**
- `root_key`: The root project name (e.g., 'webapp-api'); must be in vault's mount set, else MemoryURIError.
- `title`: Contract identifier (e.g., 'POST /items'); slugified into note filename.
- `project`: Caller's project; used to compute section heading (e.g., 'api' → `## Provider (api)`).
- `role`: 'provider' or 'consumer'; determines which section heading is rewritten.
- `content`: The caller's contract claim (validation rules, expected I/O, etc.).
- Returns: The memory:// URI of the contract note.

**Merge:** Loads the note (or creates skeleton with `source: distilled`, `type: contract`). Parses sections by role heading. Replaces only the caller's section; others preserved exactly. This is the surgical merge: only the caller's role section can be rewritten.

**Drift visibility:** Both versions coexist. When provider updates to v2 and consumer documents v1, both sit side by side for humans to reconcile.

**Enforcement:** Mount-set validation—non-members get MemoryURIError.
