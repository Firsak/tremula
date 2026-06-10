---
type: convention
scope: shared
---

# Frontmatter schema

Every note carries YAML frontmatter validated by `NoteFrontmatter`
(`src/tremula/note.py`).

```yaml
---
type: module | function | convention | decision | architecture | contract | index
scope: backend | frontend | shared      # default: shared
depends_on:  [memory://proj/path/note]  # typed relations (all optional)
implements:  [memory://proj/path/note]
decided_in:  [memory://proj/path/note]
part_of:     [memory://proj/path/note]
---
```

- `type` is required; `scope` defaults to `shared`.
- The four relation keys (`depends_on`, `implements`, `decided_in`, `part_of`)
  hold lists of [[conventions/memory-uri-addressing|memory:// URIs]]. They are
  lifted into `frontmatter.links` at load time.
- Any other frontmatter keys are preserved under `extra` — hand-authored notes
  are never silently truncated.
- `scope` exists for monorepo filtering (backend vs frontend vs shared).
