---
scope: shared
source: distilled
type: decision
---

# Frontmatter-based note metadata

Vault notes use YAML frontmatter (via `python-frontmatter`) for metadata: `type`, `scope`, and typed relations.

Bodies are markdown; source of truth is the markdown file itself, not the SQLite index (index is a rebuildable cache).
