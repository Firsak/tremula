---
depends_on:
- memory://tremula/architecture/stage-7-consolidation-splitting-self-organization
scope: shared
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

**Why:** Heat measures *actual usage*, independent of age or relational structure. Prevents:
- Archiving a heavily-consulted convention just because it's old.
- Keeping an orphaned but frequently-read decision just because it's recent.
- Treating "unlinked" as "unused" (some knowledge is accessed directly, not discovered via graph traversal).

**Trade-off — heat lives in SQLite cache, not markdown:** Usage counts are runtime observations, not derivable from markdown structure. Survive normal index rebuilds (carried forward), but reset on cache deletion. Philosophically awkward (violates "markdown is source of truth"), but unavoidable: reads are telemetry, not structure. Mitigated by: archives are never deleted (move to attic), attic is human-browsable, LLM confirms before archiving.

**How to apply:** Increment `reads` counter on access paths. Check three-signal committee before moving distilled note to attic. Keep hand-written notes untouched.
