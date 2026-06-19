"""Context injection: SessionStart block + per-prompt proactive attachment.

SessionStart puts the index (an oglavlenie, not the knowledge base) plus a few
hot notes into context. UserPromptSubmit attaches 2-3 notes scoped by the
working context. Both surfaces apply the note-lifecycle gate: a provisional
note whose subject code is absent from the working tree is withheld, while
ratified notes are always eligible and eligible notes are trust-ranked
(see :func:`_is_eligible` / ``index.eligible_notes``). A per-session sidecar
records every URI already injected so nothing is pasted twice — and it is RESET
on SessionStart, because after a compact/resume previously-injected notes may
have been squeezed out of context and must become attachable again.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from .config import Settings
from .index import Index
from .memory_uri import MemoryURIError
from .note import LifecycleStatus
from .vault import VaultService


def _is_eligible(hit, working_paths: set[str], lifecycle_enabled: bool = True) -> bool:
    """Injection gate for one search hit, reading the lifecycle columns carried
    on the hit (no extra query). Ratified notes are always eligible; provisional
    ones only when their subject code is present in the working tree. A
    provisional note with no subject binding falls through to eligible."""
    if not lifecycle_enabled or hit.status == LifecycleStatus.RATIFIED.value:
        return True
    try:
        paths = json.loads(hit.subject_paths) if hit.subject_paths else []
    except (json.JSONDecodeError, TypeError):
        paths = []
    if not paths:
        return True
    return bool(set(paths) & set(working_paths))


def build_injection(
    mounts: dict[str, Path],
    project: str | None,
    index: Index,
    settings: Settings,
    working_paths: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Assemble the SessionStart context block; returns (block, injected_uris).

    ``working_paths`` are the files present/changed in the working tree right
    now; provisional notes whose subject code is absent from it are withheld.
    """
    if not project or project not in mounts:
        return "", []
    working_paths = working_paths or set()

    parts: list[str] = []
    uris: list[str] = []
    index_md = Path(mounts[project]) / "_index.md"
    if index_md.exists():
        # Inject the body only — YAML frontmatter is vault plumbing, not context.
        post = frontmatter.loads(index_md.read_text(encoding="utf-8"))
        parts.append(post.content.strip())
        uris.append(f"memory://{project}/_index")

    # Hot notes: trust-ranked + working-tree-gated, excluding the index itself.
    hot = [
        r for r in index.eligible_notes(
            working_paths, lifecycle_enabled=settings.lifecycle_enabled
        )
        if not r["uri"].endswith("/_index")
    ]
    hot = hot[: settings.hot_notes]
    if hot:
        lines = [f"- {r['uri']} — {r['title']} [{r['type']}]" for r in hot]
        parts.append("## Recently updated memory\n" + "\n".join(lines))
        uris.extend(r["uri"] for r in hot)

    block = "\n\n".join(parts).strip()
    if len(block) > settings.max_injection_chars:
        block = block[: settings.max_injection_chars].rstrip() + "\n… (truncated)"
    return block, uris


# ---- injected-URI sidecar (dedupe across one session) -------------------------

def injected_path(session_file: str | Path) -> Path:
    return Path(session_file).with_suffix(".injected.json")


def load_injected(session_file: str | Path) -> set[str]:
    try:
        data = json.loads(injected_path(session_file).read_text())
        return set(data) if isinstance(data, list) else set()
    except (OSError, json.JSONDecodeError):
        return set()


def save_injected(session_file: str | Path, uris) -> None:
    """Overwrite the sidecar — used by SessionStart to RESET dedupe state."""
    try:
        path = injected_path(session_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(set(uris))))
    except OSError:
        pass  # dedupe is an optimization; never fail a hook over it


def record_injected(session_file: str | Path, new_uris) -> None:
    save_injected(session_file, load_injected(session_file) | set(new_uris))


# ---- proactive attachment (UserPromptSubmit) -----------------------------------

def build_attachment(
    vault: VaultService,
    terms: list[str],
    exclude: set[str],
    settings: Settings,
    working_paths: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Pick up to N not-yet-injected notes matching the working context.

    Returns (block, attached_uris); both empty when nothing relevant is left.
    Provisional notes whose subject code is absent from ``working_paths`` are
    skipped (the gate reads lifecycle columns off each hit — no extra query).
    """
    if not terms:
        return "", []
    working_paths = working_paths or set()
    hits = vault.index.search_any(terms, limit=settings.attach_notes * 4)
    chunks: list[str] = []
    attached: list[str] = []
    used = 0
    for hit in hits:
        if len(attached) >= settings.attach_notes:
            break
        if hit.uri in exclude or hit.uri.endswith("/_index"):
            continue
        if not _is_eligible(hit, working_paths, settings.lifecycle_enabled):
            continue
        try:
            note = vault.read_note(hit.uri)
        except (MemoryURIError, FileNotFoundError):
            continue
        body = note["body"].strip()
        if len(body) > settings.attach_note_chars:
            body = body[: settings.attach_note_chars].rstrip() + " …"
        chunk = f"### {note['title']}\n<{hit.uri}>\n{body}"
        if used + len(chunk) > settings.attach_max_chars and attached:
            break
        chunks.append(chunk)
        attached.append(hit.uri)
        used += len(chunk)
    if not attached:
        return "", []
    header = "## Possibly relevant memory (tremula, by working context)\n\n"
    block = (header + "\n\n".join(chunks))[: settings.attach_max_chars + len(header)]
    return block, attached
