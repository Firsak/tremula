"""The atomic unit of memory: one note = one fact/entity.

A note is a markdown file with YAML frontmatter. Frontmatter carries the note
``type``, its ``scope`` (for monorepo filtering), and typed relations to other
notes expressed as ``memory://`` URIs. The markdown body is the human- and
agent-readable content. This module parses notes via ``python-frontmatter`` and
validates frontmatter with pydantic.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import frontmatter
from pydantic import BaseModel, Field, field_validator

from .memory_uri import MemoryURI, is_memory_uri


class NoteType(StrEnum):
    MODULE = "module"
    FUNCTION = "function"
    CONVENTION = "convention"
    DECISION = "decision"
    ARCHITECTURE = "architecture"
    CONTRACT = "contract"  # lives in a root vault
    INDEX = "index"  # _index.md, split parents


class Scope(StrEnum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    SHARED = "shared"


# Typed link relations carried in frontmatter (plan §1).
RELATIONS = ("depends_on", "implements", "decided_in", "part_of")


class NoteFrontmatter(BaseModel):
    """Validated frontmatter for a note.

    ``links`` holds the typed relations, each a list of ``memory://`` URIs.
    Unknown frontmatter keys are preserved in ``extra`` so hand-authored notes
    are never silently truncated.
    """

    type: NoteType
    scope: Scope = Scope.SHARED
    links: dict[str, list[str]] = Field(default_factory=dict)
    extra: dict = Field(default_factory=dict)

    @field_validator("links")
    @classmethod
    def _validate_links(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for relation, targets in value.items():
            if relation not in RELATIONS:
                raise ValueError(
                    f"unknown relation {relation!r}; allowed: {RELATIONS}"
                )
            for target in targets:
                if not is_memory_uri(target):
                    raise ValueError(
                        f"link target is not a memory:// URI: {target!r}"
                    )
        return value


class Note(BaseModel):
    """A parsed note: its address, validated frontmatter, and body."""

    uri: MemoryURI
    frontmatter: NoteFrontmatter
    body: str

    model_config = {"arbitrary_types_allowed": True}

    @property
    def title(self) -> str:
        # First markdown heading, else the note id.
        for line in self.body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return self.uri.note_id

    def linked_uris(self) -> list[MemoryURI]:
        out: list[MemoryURI] = []
        for targets in self.frontmatter.links.values():
            out.extend(MemoryURI.parse(t) for t in targets)
        return out


def _split_links(meta: dict) -> tuple[dict[str, list[str]], dict]:
    """Pull known relation keys out of raw frontmatter into ``links``."""
    links: dict[str, list[str]] = {}
    extra: dict = {}
    for key, value in meta.items():
        if key in RELATIONS:
            links[key] = list(value) if isinstance(value, (list, tuple)) else [value]
        elif key not in ("type", "scope"):
            extra[key] = value
    return links, extra


def load_note(path: str | Path, project: str) -> Note:
    """Load and validate a note file for the given project key.

    The note's URI is derived from its path relative to the vault root. We
    locate the vault root by walking up to the directory whose child is the
    note's top-level category (e.g. ``decisions/``); callers that know the
    vault root should prefer :func:`load_note_in_vault`.
    """
    path = Path(path)
    return load_note_in_vault(path, vault_root=_guess_vault_root(path), project=project)


def load_note_in_vault(path: str | Path, vault_root: str | Path, project: str) -> Note:
    """Load a note, deriving its ``memory://`` URI from its path under ``vault_root``."""
    path = Path(path)
    vault_root = Path(vault_root)
    rel = path.relative_to(vault_root).with_suffix("")
    uri = MemoryURI(project=project, path="/".join(rel.parts))

    post = frontmatter.load(path)
    links, extra = _split_links(post.metadata)
    fm = NoteFrontmatter(
        type=post.metadata.get("type", NoteType.INDEX.value),
        scope=post.metadata.get("scope", Scope.SHARED.value),
        links=links,
        extra=extra,
    )
    return Note(uri=uri, frontmatter=fm, body=post.content)


def _guess_vault_root(path: Path) -> Path:
    """Best-effort vault root: nearest ancestor named ``tremula-vault``."""
    for parent in path.resolve().parents:
        if parent.name == "tremula-vault":
            return parent
    # Fall back to the file's parent directory.
    return path.resolve().parent
