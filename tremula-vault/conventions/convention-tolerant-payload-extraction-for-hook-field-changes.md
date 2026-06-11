---
depends_on:
- memory://tremula/architecture/stage-4-proactive-memory-attachment-via-working-context-extraction
scope: backend
source: distilled
type: convention
---

# Convention: Tolerant payload extraction for hook field changes

The ambient hooks (capture, injection, distiller) read Claude Code lifecycle events, whose payloads have a fixed structure (e.g., `PostToolUse.tool_input.file_path`). Claude Code's hook schema may evolve over time.

**Rule:** Extract values (especially file paths) from hook payloads *tolerantly*: scan the payload recursively for any string matching a path pattern (starts with `/`, `.`, or `~`; contains `/` separators) rather than hardcoding a specific field lookup.

**Why:** Hardcoded field paths fail silently when renamed. Silent failure — hooks that stop attaching memory after a Claude Code update — is invisible until the user notices. Tolerant extraction degrades gracefully: if a field is renamed or missing, extraction returns fewer matches (fail open) instead of zero.

**How to apply:** Define a recursive path scanner that walks the payload dict/list and collects all string values matching the path pattern. Return the first N matches (typically 1–3 recent files). If payloads evolve, the scanner adapts automatically without code changes.

**Example:**
```python
def extract_paths(payload, max_count=5):
    """Recursively scan payload for path-like strings."""
    paths = []
    def visit(obj):
        if isinstance(obj, dict):
            for v in obj.values(): visit(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj: visit(item)
        elif isinstance(obj, str) and looks_like_path(obj):
            paths.append(obj)
    visit(payload)
    return paths[:max_count]
```
