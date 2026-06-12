---
scope: backend
source: distilled
type: decision
---

# Decision: Heat tracking — usage metrics for stale cleanup

**Problem:** Stale cleanup must distinguish truly dead notes from old-but-valuable ones that remain consulted regularly. Pure age-based archival kills precious decisions; pure link-based keeps orphaned but actively-used notes.

**Decision:** Three-signal committee determines if a distilled note is dead:

1. **Heat**: `reads` counter (0 = never accessed) + `last_read` timestamp. Incremented on every access (read_note tool, get_context inclusion, auto-injection into prompts).
2. **Links**: other notes link to it (structural value).
3. **Age**: older than 14+ days (configurable).

Note becomes archive candidate **only when all three signals agree dead**. Hand-written notes are exempt regardless of heat.

**Implementation — track flag:** Heat increments only on *user-facing reads*. The read_note tool and get_context accept `track=True` (default); machinery (distiller snapshots, revision pass scans) pass `track=False`. This ensures heat measures actual human consultation, not internal bookkeeping.

**Why:** Heat measures *actual usage*, independent of age or relational structure. Prevents:
- Archiving a heavily-consulted convention just because it's old.
- Keeping an orphaned but frequently-read decision just because it's recent.
- Treating "unlinked" as "unused" (some knowledge is accessed directly, not discovered via graph traversal).

**Trade-off — heat lives in SQLite cache, not markdown:** Usage counts are runtime state; deleting the cache database resets heat to zero (documented in config). Archived notes carry `archived_at` and `archived_reason` in frontmatter for human audit.
