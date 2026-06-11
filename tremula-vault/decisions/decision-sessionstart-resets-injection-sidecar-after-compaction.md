---
depends_on:
- memory://tremula/architecture/two-loops
- memory://tremula/decisions/distill-cadence
scope: backend
source: distilled
type: decision
---

# Decision: SessionStart resets injection sidecar after compaction

**Context:** The `UserPromptSubmit` hook uses a per-session sidecar file (`<session>.inject.json`) to deduplicate injected notes, avoiding re-injection of the same note twice in a conversation. After a context compact (where the context window is cleared to continue), previously injected notes were recorded in the sidecar as "already injected," so they would never be re-injected even though they no longer exist in the conversation context.

**Bug:** Compaction orphans memory: notes vanish from context but the sidecar still marks them as injected, locking them out from future reinjection.

**Decision:** SessionStart fires both at session start *and* again after a compact. When it fires after a compact, it resets the sidecar fresh (truncates, does not append) so memory can be re-injected into the new context window.

**How to apply:** In `injection.py`, detect compact events (either via explicit marker or by observing context size reset to near-zero). On SessionStart after a compact, truncate the sidecar instead of appending. Notes are re-eligible for injection in the new context.

**Consequence:** Memory remains re-injectable after compaction, solving the blind spot where notes could be permanently locked out.
