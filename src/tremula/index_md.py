"""Mechanical maintenance of the auto-section in ``_index.md``.

``_index.md`` is human-curated — but new note files must surface in it
automatically, no matter who created them (the distiller, an agent, a human
dropping a file into the vault). The compromise is a machine-owned section
between markers:

    <!-- tremula:auto -->
    ...generated list of notes not yet linked above...
    <!-- /tremula:auto -->

Everything outside the markers is never touched. The section is regenerated
deterministically (no LLM): it lists every note that is not referenced in the
manual part. Moving a link out of the section into a curated heading is the
human act of endorsing the note — the next sync then drops it from the
auto-list automatically.
"""

from __future__ import annotations

import re
from pathlib import Path

from .note import load_note_in_vault

AUTO_BEGIN = "<!-- tremula:auto -->"
AUTO_END = "<!-- /tremula:auto -->"
_HEADER = "## Unreviewed notes (auto-listed; move a link up to endorse it)"

# [[path]] or [[path|label]] wikilinks, and memory:// URIs.
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]")
_MEMORY_RE = re.compile(r"memory://([A-Za-z0-9_-]+)/([A-Za-z0-9_./-]+)")


def _linked_paths(manual_text: str, project: str) -> set[str]:
    """Note paths (vault-relative, no extension) referenced in the manual part."""
    linked = {match.strip().removesuffix(".md")
              for match in _WIKILINK_RE.findall(manual_text)}
    for proj, path in _MEMORY_RE.findall(manual_text):
        if proj == project:
            linked.add(path.removesuffix(".md"))
    return linked


def _split(text: str) -> tuple[str, str]:
    """Split index text into (before_auto, after_auto), dropping the old section."""
    begin = text.find(AUTO_BEGIN)
    if begin == -1:
        return text.rstrip() + "\n", ""
    end = text.find(AUTO_END, begin)
    after = text[end + len(AUTO_END):] if end != -1 else ""
    return text[:begin].rstrip() + "\n", after.lstrip("\n")


def sync_index_auto_section(vault_root: str | Path, project: str) -> bool:
    """Regenerate the auto-section; returns True if ``_index.md`` changed."""
    vault_root = Path(vault_root)
    index_path = vault_root / "_index.md"
    if not index_path.exists():
        return False  # bootstrap (Stage 5) creates the index; nothing to sync into

    text = index_path.read_text(encoding="utf-8")
    before, after = _split(text)
    linked = _linked_paths(before + after, project)

    entries: list[str] = []
    for path in sorted(vault_root.rglob("*.md")):
        parts = path.relative_to(vault_root).with_suffix("").parts
        rel = "/".join(parts)
        if rel == "_index" or rel in linked or "attic" in parts:
            continue
        try:
            note = load_note_in_vault(path, vault_root, project=project)
        except Exception:
            continue  # malformed/mid-write file: it can be listed next sync
        tag = note.frontmatter.type.value
        if note.frontmatter.source == "distilled":
            tag += ", distilled"
        entries.append(f"- [[{rel}]] — {note.title} [{tag}]")

    if entries:
        section = f"{AUTO_BEGIN}\n{_HEADER}\n" + "\n".join(entries) + f"\n{AUTO_END}\n"
    else:
        section = f"{AUTO_BEGIN}\n{AUTO_END}\n"

    new_text = before + "\n" + section + (after if not after else after.rstrip() + "\n")
    if new_text == text:
        return False
    index_path.write_text(new_text, encoding="utf-8")
    return True
