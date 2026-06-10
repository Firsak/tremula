"""Global note addressing: ``memory://project/path/note``.

Tremula uses global URIs from day one instead of local Obsidian ``[[title]]``
wikilinks, so a note in one vault (ramet or root) can reference a note in
another vault unambiguously. Resolution to a filesystem path requires a mapping
of project name -> vault root, which the registry provides (Stage 2). Stage 1
ships the parser plus a single-project resolver.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SCHEME = "memory://"

# project segment: a registry key (letters, digits, dash, underscore)
# path segment: one or more slash-separated note-path components
_URI_RE = re.compile(
    r"^memory://(?P<project>[A-Za-z0-9_-]+)/(?P<path>[A-Za-z0-9_./-]+?)(?:\.md)?$"
)
# One path segment: must not start with a dot, so ``.``, ``..`` and dotfiles are
# unrepresentable — a memory:// URI can never escape its vault root.
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


class MemoryURIError(ValueError):
    """Raised when a string is not a well-formed ``memory://`` URI."""


@dataclass(frozen=True)
class MemoryURI:
    """A parsed ``memory://project/path/note`` address.

    ``project`` is a registry key. ``path`` is the note path relative to that
    project's vault root, without the ``.md`` extension (e.g.
    ``decisions/name``). ``note_id`` is the final path segment.
    """

    project: str
    path: str

    @classmethod
    def parse(cls, raw: str) -> MemoryURI:
        match = _URI_RE.match(raw.strip())
        if not match:
            raise MemoryURIError(f"not a valid memory:// URI: {raw!r}")
        path = match["path"].strip("/")
        if not path:
            raise MemoryURIError(f"memory:// URI has empty note path: {raw!r}")
        for segment in path.split("/"):
            if not _SEGMENT_RE.match(segment):
                raise MemoryURIError(
                    f"invalid path segment {segment!r} in {raw!r} "
                    "(segments must start with a letter/digit/underscore)"
                )
        return cls(project=match["project"], path=path)

    @property
    def note_id(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    def __str__(self) -> str:
        return f"{SCHEME}{self.project}/{self.path}"

    def relative_file(self) -> Path:
        """The vault-relative markdown file path for this URI."""
        return Path(*self.path.split("/")).with_suffix(".md")


def is_memory_uri(value: str) -> bool:
    return bool(_URI_RE.match(value.strip()))


def resolve(uri: str | MemoryURI, project_roots: dict[str, Path]) -> Path:
    """Resolve a ``memory://`` URI to an absolute markdown file path.

    ``project_roots`` maps a project/root key to its vault directory. Raises
    :class:`MemoryURIError` if the URI's project is not in the mapping (i.e.
    outside the current mount set).
    """
    parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)
    root = project_roots.get(parsed.project)
    if root is None:
        raise MemoryURIError(
            f"project {parsed.project!r} is not in the mount set "
            f"(known: {sorted(project_roots)})"
        )
    root_resolved = Path(root).resolve()
    resolved = (root_resolved / parsed.relative_file()).resolve()
    # Belt and suspenders on top of segment validation: a resolved note path
    # must stay inside its vault root, or the mount-set boundary means nothing.
    if not resolved.is_relative_to(root_resolved):
        raise MemoryURIError(f"URI escapes its vault root: {parsed}")
    return resolved
