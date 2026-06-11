---
depends_on:
- memory://tremula/modules/tremula-memory-uri
- memory://tremula/modules/tremula-vault
scope: shared
source: distilled
type: module
---

# tremula.contracts

Manages contract notes in federated root vaults shared between two projects. Ensures each project maintains its own isolated section (provider or consumer) without interfering with the other's claims.

## Public API
- `section_heading(role, project)` — Generate a section heading for a contract role and project name.
- `upsert_contract_section(vault, root_key, title, project, role, content)` — Create or update this project's section of a contract note; returns the note's memory:// URI.
