"""Working-context extraction for the retrieval funnel (plan §5.3).

Proactive note attachment is scoped by what the session is actually touching —
the paths of recent file operations, git status, and cwd — never by the words
of the prompt. This module turns those signals into search terms.

Everything here is hot-path code (runs inside the UserPromptSubmit hook):
no LLM, bounded subprocess use, fail-soft everywhere.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .capture import read_session

# Payload keys whose string values are treated as file paths. Claude Code's
# PostToolUse payloads carry tool input under names like file_path / path /
# notebook_path; extraction is recursive so nesting and renames of the
# surrounding structure don't break it.
PATH_KEYS = {"file_path", "filepath", "filePath", "path", "notebook_path", "notebookPath"}

# Structural path segments that carry no topical signal.
STOPWORDS = {
    "src", "lib", "libs", "app", "apps", "test", "tests", "spec", "specs",
    "pkg", "packages", "node_modules", "dist", "build", "out", "target",
    "py", "js", "ts", "tsx", "md", "txt", "json", "yaml", "yml", "toml",
}


def extract_paths_from_events(events: list[dict], max_paths: int = 10) -> list[str]:
    """Most-recent-first distinct file paths mentioned in captured events."""
    found: list[str] = []

    def walk(value) -> None:
        if len(found) >= max_paths * 3:  # bound the scan
            return
        if isinstance(value, dict):
            for key, val in value.items():
                if key in PATH_KEYS and isinstance(val, str) and _looks_like_path(val):
                    if val not in found:
                        found.append(val)
                else:
                    walk(val)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for event in reversed(events):  # newest first
        walk(event.get("payload", {}))
        if len(found) >= max_paths:
            break
    return found[:max_paths]


def _looks_like_path(value: str) -> bool:
    return ("/" in value or "." in value) and len(value) < 500 and "\n" not in value


def git_changed_files(repo_root: str | Path, timeout: float = 0.5) -> list[str]:
    """Paths reported changed by ``git status --porcelain``; [] on any failure."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return []
    except Exception:
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        entry = line[3:].strip().strip('"')
        if " -> " in entry:  # rename: keep the new name
            entry = entry.split(" -> ", 1)[1]
        if entry:
            paths.append(entry)
    return paths


def derive_terms(paths: list[str], max_terms: int = 12) -> list[str]:
    """Turn file paths into search terms: name stems + meaningful dir names.

    ``src/tremula/memory_uri.py`` -> ``memory``, ``uri``, ``tremula``.
    Order preserves the recency of the source paths.
    """
    terms: list[str] = []
    for raw in paths:
        path = Path(raw)
        candidates = [path.stem, *[p.name for p in path.parents if p.name]]
        for candidate in candidates:
            for token in re.split(r"[^A-Za-z0-9]+", candidate):
                token = token.lower()
                if len(token) >= 3 and token not in STOPWORDS and token not in terms:
                    terms.append(token)
                if len(terms) >= max_terms:
                    return terms
    return terms


def working_context(
    session_path: str | Path | None,
    repo_root: str | Path | None,
    max_paths: int = 10,
) -> dict:
    """Assemble the working context: recent session paths + git status.

    Returns ``{"paths": [...], "terms": [...]}``; both empty when there is no
    signal (the caller then attaches nothing).
    """
    paths: list[str] = []
    if session_path is not None:
        try:
            paths.extend(extract_paths_from_events(read_session(session_path), max_paths))
        except Exception:
            pass
    if repo_root is not None:
        for path in git_changed_files(repo_root):
            if path not in paths:
                paths.append(path)
    paths = paths[: max_paths * 2]
    return {"paths": paths, "terms": derive_terms(paths)}
