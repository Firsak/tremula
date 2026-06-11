---
depends_on:
- memory://tremula/modules/tremula-cli
scope: shared
source: distilled
type: module
---

# tremula.__main__

Entry point for running the CLI via `python -m tremula`. Delegates to the main CLI handler; used by the detached distiller spawn.
