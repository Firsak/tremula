---
type: convention
scope: shared
depends_on: [memory://tremula/decisions/vault-at-repo-root]
---

# Global addressing: memory:// from day one

Notes reference each other with global URIs, not local Obsidian `[[title]]`
wikilinks:

```
memory://project/path/note
```

- `project` is a registry key (a `ramet` or a `root`).
- `path` is the note path relative to that project's vault root, without the
  `.md` extension (e.g. `decisions/name-tremula`).

Why global from day one: a `root` (bridge vault) node must be referenceable from
two different ramets at once, and graph traversal crosses vault boundaries via
these URIs within the current mount set. Local wikilinks cannot express
cross-vault links, so we never start with them.

Parsing and resolution live in `src/tremula/memory_uri.py`. Resolution needs a
`project -> vault root` mapping; Stage 2's registry supplies it, and anything
outside the mount set is unresolvable by design.

Security: path segments must start with a letter/digit/underscore — `.`,`..`
and dotfiles are unrepresentable, so a URI can never address a file outside its
vault. `resolve()` additionally verifies the resolved path stays inside the
vault root. Both checks exist because the mount-set boundary is an access-control
line, not a convention.
