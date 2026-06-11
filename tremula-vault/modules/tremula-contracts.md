---
depends_on:
- memory://tremula/modules/tremula-vault
- memory://tremula/modules/tremula-note
scope: shared
source: distilled
type: module
---

# tremula.contracts

Manages per-side contract sections in shared root vaults. Enables safe, decentralized coordination across federated projects: each project owns exactly one section per contract, preventing merge conflicts and making drift visible.

## Public API

- `upsert_contract_section(vault: VaultService, root_key: str, title: str, project: str, role: str, content: str) -> str` — Create or surgically update a contract section in a root vault. `role` is 'provider' or 'consumer'; only the caller's section is replaced, preserving all other projects' sections. Returns the memory:// URI. Raises MemoryURIError if root is not in the vault's mount set (non-member access).
