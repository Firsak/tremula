"""SessionStart injection: put memory in context from the first token.

The agent shouldn't have to decide whether to look for memory — the index
(``_index.md``) plus a few hot notes are injected at session start. We inject an
oglavlenie (table of contents), not the whole knowledge base: the funnel's job
is to keep this small. Size is capped as a feature, not a limitation.
"""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .index import Index


def build_injection(
    mounts: dict[str, Path],
    project: str | None,
    index: Index,
    settings: Settings,
) -> str:
    """Assemble the SessionStart context block for the current mount set."""
    if not project or project not in mounts:
        return ""

    parts: list[str] = []
    index_md = Path(mounts[project]) / "_index.md"
    if index_md.exists():
        parts.append(index_md.read_text(encoding="utf-8").strip())

    # Hot notes: most recently modified, excluding the index itself.
    hot = [r for r in index.all_notes() if not r["uri"].endswith("/_index")]
    hot = hot[: settings.hot_notes]
    if hot:
        lines = [f"- {r['uri']} — {r['title']} [{r['type']}]" for r in hot]
        parts.append("## Recently updated memory\n" + "\n".join(lines))

    block = "\n\n".join(parts).strip()
    if len(block) > settings.max_injection_chars:
        block = block[: settings.max_injection_chars].rstrip() + "\n… (truncated)"
    return block
