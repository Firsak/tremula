---
depends_on:
- memory://tremula/modules/tremula-config
scope: shared
source: distilled
type: module
---

# tremula.capture

Hot-path session capture via append-only NDJSON that never blocks or fails. Clips payloads to prevent balloon growth, with expensive LLM distillation deferred to a separate process.

## Public API
- `session_file(project, session_id)` — Generate safe session file path for a project and session ID
- `clip_payload(value, max_str=2000)` — Recursively truncate strings and lists to prevent payload balloon
- `append_event(project, session_id, event, payload)` — Append event to session NDJSON; never raises, returns success bool
- `read_session(path)` — Read entire NDJSON session file into event list
- `read_session_since(path, offset)` — Incremental read: fetch events since byte offset, return (events, new_offset)
