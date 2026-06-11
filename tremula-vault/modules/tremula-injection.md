---
depends_on:
- memory://tremula/modules/tremula-config
- memory://tremula/modules/tremula-index
- memory://tremula/modules/tremula-memory-uri
- memory://tremula/modules/tremula-vault
scope: shared
source: distilled
type: module
---

# tremula.injection

Manages context injection for SessionStart and UserPromptSubmit hooks. Builds context blocks from the vault index and hot notes, maintains a per-session sidecar to deduplicate injected URIs across the session, and attaches relevant notes scoped by working context.

## Public API
- `build_injection(mounts, project, index, settings)` — Assemble SessionStart context block with index and hot notes; returns (block, injected_uris).
- `injected_path(session_file)` — Return path to the injected-URI sidecar for a session.
- `load_injected(session_file)` — Load set of already-injected URIs from sidecar to detect duplicates.
- `save_injected(session_file, uris)` — Overwrite sidecar with new URI set; SessionStart uses this to reset dedupe state.
- `record_injected(session_file, new_uris)` — Append new URIs to existing sidecar set.
- `build_attachment(vault, terms, exclude, settings)` — Pick not-yet-injected notes matching working context; returns (block, attached_uris).
