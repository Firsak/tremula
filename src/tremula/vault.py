"""VaultService — the write/read/search engine shared by the MCP server and the
distiller.

Every mutation writes markdown first (the source of truth), then updates the
SQLite index. All access is scoped to a session's mount set: a URI outside the
set is unresolvable, so tools and the distiller physically cannot touch another
project's private notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from .index import Index
from .memory_uri import MemoryURI, MemoryURIError, resolve
from .note import RELATIONS, Note, NoteType, Scope, load_note_in_vault

# Which vault folder each note type lives in.
FOLDER_BY_TYPE: dict[NoteType, str] = {
    NoteType.MODULE: "modules",
    NoteType.FUNCTION: "functions",
    NoteType.CONVENTION: "conventions",
    NoteType.DECISION: "decisions",
    NoteType.ARCHITECTURE: "architecture",
    NoteType.CONTRACT: "contracts",
    NoteType.INDEX: ".",  # top level of the vault
}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "note"


@dataclass
class ContextResult:
    """A get_context answer: the seed hits plus their graph neighbors."""

    topic: str
    seeds: list[str] = field(default_factory=list)
    neighbors: list[str] = field(default_factory=list)
    content: str = ""


class VaultService:
    """Mount-set-scoped operations over notes. Markdown first, index second."""

    def __init__(self, mounts: dict[str, Path], index: Index, project: str | None = None):
        self.mounts = {k: Path(v) for k, v in mounts.items()}
        self.index = index
        self.project = project  # default target ramet for writes

    # ---- helpers ------------------------------------------------------------

    def _path_for(self, uri: MemoryURI) -> Path:
        return resolve(uri, self.mounts)

    def target_uri(self, title: str, type: str, project: str | None = None) -> str:
        """The memory:// URI a write with this title+type would land on (no write)."""
        target = self._require_project(project)
        folder = FOLDER_BY_TYPE[NoteType(type)]
        rel = f"{folder}/{slugify(title)}" if folder != "." else slugify(title)
        return str(MemoryURI(project=target, path=rel))

    def _require_project(self, project: str | None) -> str:
        target = project or self.project
        if target is None:
            raise ValueError("no target project for write (session has no project)")
        if target not in self.mounts:
            raise MemoryURIError(
                f"project {target!r} not in mount set {sorted(self.mounts)}"
            )
        return target

    def _reindex(self, path: Path, project: str) -> Note:
        note = load_note_in_vault(path, self.mounts[project], project=project)
        stat = path.stat()
        self.index.upsert_note(note, body=note.body, mtime=stat.st_mtime,
                               size=stat.st_size)
        return note

    # ---- writes -------------------------------------------------------------

    def write_note(
        self,
        title: str,
        content: str,
        type: str = "module",
        scope: str = "shared",
        links: dict[str, list[str]] | None = None,
        project: str | None = None,
        source: str = "manual",
        protect: bool = False,
        status: str = "ratified",
        confirmation_count: int = 0,
        subject_paths: list[str] | None = None,
        subject_symbols: list[str] | None = None,
    ) -> str:
        """Create or overwrite a note; returns its ``memory://`` URI.

        ``protect=True`` refuses to overwrite a human-authored note (one whose
        ``source`` is not ``distilled``). The distiller passes ``protect=True``
        and ``source="distilled"`` so it can update its own notes but never
        clobber hand-written ones.
        """
        target = self._require_project(project)
        ntype = NoteType(type)
        Scope(scope)  # validate
        links = links or {}
        for relation in links:
            if relation not in RELATIONS:
                raise ValueError(f"unknown relation {relation!r}; allowed {RELATIONS}")

        folder = FOLDER_BY_TYPE[ntype]
        rel = f"{folder}/{slugify(title)}" if folder != "." else slugify(title)
        uri = MemoryURI(project=target, path=rel)
        path = self._path_for(uri)

        if protect and path.exists():
            existing = load_note_in_vault(path, self.mounts[target], target)
            if existing.frontmatter.source != "distilled":
                raise PermissionError(
                    f"refusing to overwrite manual note {uri} (source="
                    f"{existing.frontmatter.source!r})"
                )

        path.parent.mkdir(parents=True, exist_ok=True)
        body = content if content.lstrip().startswith("#") else f"# {title}\n\n{content}"
        post = frontmatter.Post(
            body, type=ntype.value, scope=scope, source=source,
            status=status, confirmation_count=confirmation_count,
            subject_paths=subject_paths or [], subject_symbols=subject_symbols or [],
            **links,
        )
        path.write_text(frontmatter.dumps(post) + "\n")
        self._reindex(path, target)
        return str(uri)

    def link_notes(self, src: str, dst: str, relation: str) -> str:
        """Add a typed edge ``src --relation--> dst`` to src's frontmatter."""
        if relation not in RELATIONS:
            raise ValueError(f"unknown relation {relation!r}; allowed {RELATIONS}")
        src_uri = MemoryURI.parse(src)
        MemoryURI.parse(dst)  # validate dst shape
        path = self._path_for(src_uri)
        if not path.exists():
            raise FileNotFoundError(f"note not found: {src}")
        post = frontmatter.load(path)
        existing = post.metadata.get(relation, [])
        if not isinstance(existing, list):
            existing = [existing]
        if dst not in existing:
            existing.append(dst)
        post.metadata[relation] = existing
        path.write_text(frontmatter.dumps(post) + "\n")
        self._reindex(path, src_uri.project)
        return src

    def split_note(self, uri: str) -> list[str]:
        """Split an oversized note by its ``##`` sections into child notes.

        The parent becomes an index linking to the children (Zettelkasten: a
        grown note becomes a table of contents).
        """
        parent_uri = MemoryURI.parse(uri)
        path = self._path_for(parent_uri)
        if not path.exists():
            raise FileNotFoundError(f"note not found: {uri}")
        parent = load_note_in_vault(path, self.mounts[parent_uri.project], parent_uri.project)

        preamble, sections = _split_sections(parent.body)
        if len(sections) < 2:
            return []  # nothing to split

        ptype = parent.frontmatter.type.value
        pscope = parent.frontmatter.scope.value
        psource = parent.frontmatter.source
        child_uris: list[str] = []
        toc_lines: list[str] = []
        for heading, sect_body in sections:
            child_uri = self.write_note(
                title=f"{parent.title}: {heading}",
                content=f"# {heading}\n\n{sect_body.strip()}",
                type=ptype,
                scope=pscope,
                links={"part_of": [str(parent_uri)]},
                project=parent_uri.project,
                source=psource,  # children inherit provenance (and protection)
            )
            child_uris.append(child_uri)
            toc_lines.append(f"- [[{MemoryURI.parse(child_uri).path}]]")

        # The parent becomes an index but keeps its preamble (the intro text
        # before the first ##) and ALL its frontmatter — splitting reorganizes,
        # it must never lose content, links, or provenance.
        intro = preamble.strip() or f"# {parent.title}"
        new_body = f"{intro}\n\n{parent.title} index:\n\n" + "\n".join(toc_lines) + "\n"
        post = frontmatter.Post(
            new_body, type=ptype, scope=pscope, source=psource,
            **parent.frontmatter.links,
        )
        path.write_text(frontmatter.dumps(post) + "\n")
        self._reindex(path, parent_uri.project)
        return child_uris

    # ---- reads --------------------------------------------------------------

    def read_note(self, uri: str, track: bool = True) -> dict:
        """Return a note's metadata + body, or raise if outside the mount set.

        ``track`` bumps heat telemetry (reads/last_read) — true for user-facing
        reads (MCP tool, get_context, attach); internal scans (distiller
        existing-notes snapshot, revision pass) pass False so machinery doesn't
        masquerade as usage.
        """
        parsed = MemoryURI.parse(uri)
        path = resolve(parsed, self.mounts)  # raises MemoryURIError if out-of-set
        if not path.exists():
            raise FileNotFoundError(f"note not found: {uri}")
        note = load_note_in_vault(path, self.mounts[parsed.project], parsed.project)
        if track:
            self.index.touch(uri)
        return {
            "uri": str(note.uri),
            "type": note.frontmatter.type.value,
            "scope": note.frontmatter.scope.value,
            "source": note.frontmatter.source,
            "status": note.frontmatter.status.value,
            "confirmation_count": note.frontmatter.confirmation_count,
            "subject_paths": note.frontmatter.subject_paths,
            "subject_symbols": note.frontmatter.subject_symbols,
            "title": note.title,
            "links": note.frontmatter.links,
            "body": note.body,
        }

    def search(self, query: str, scope: str | None = None, limit: int = 10) -> list[dict]:
        # Pull-based cache consistency: revalidate the index against the files
        # before querying, so mid-session edits (human, other session,
        # distiller) are visible without a rebuild or notification channel.
        self.index.refresh(self.mounts)
        return [
            {"uri": h.uri, "title": h.title, "type": h.type, "snippet": h.snippet}
            for h in self.index.search(query, scope=scope, limit=limit)
        ]

    def existing_notes(self, max_notes: int = 40, body_chars: int = 1200) -> list[dict]:
        """A compact snapshot of current notes for the distiller to read before
        writing — so it can UPDATE the right note instead of regenerating a
        thinner duplicate that clobbers by slug collision."""
        self.index.refresh(self.mounts)
        out: list[dict] = []
        for row in self.index.all_notes()[:max_notes]:
            try:
                note = self.read_note(row["uri"], track=False)  # machinery, not usage
            except (MemoryURIError, FileNotFoundError):
                continue
            body = note["body"].strip()
            out.append({
                "uri": note["uri"],
                "title": note["title"],
                "type": note["type"],
                "source": note["source"],
                "body": body[:body_chars] + (" …" if len(body) > body_chars else ""),
            })
        return out

    def get_context(self, topic: str, depth: int = 1, max_notes: int = 6) -> ContextResult:
        """FTS seed + graph expansion: find the topic, then pull its neighbors.

        The on-demand step of the retrieval funnel ("search finds what you
        asked for, the graph finds what you forgot to ask"). The per-prompt
        working-context attach lives in the hooks layer.
        """
        self.index.refresh(self.mounts)
        hits = self.index.search(topic, limit=3)
        seeds = [h.uri for h in hits]
        neighbor_uris: list[str] = []
        for seed in seeds:
            # sorted: neighbors() returns a set; keep output deterministic.
            for n in sorted(self.index.neighbors(seed, depth=depth)):
                if n not in seeds and n not in neighbor_uris:
                    neighbor_uris.append(n)

        chunks: list[str] = []
        for uri in [*seeds, *neighbor_uris][:max_notes]:
            try:
                note = self.read_note(uri)
            except (MemoryURIError, FileNotFoundError):
                continue
            chunks.append(f"## {note['title']}\n<{uri}>\n\n{note['body'].strip()}")
        return ContextResult(
            topic=topic,
            seeds=seeds,
            neighbors=neighbor_uris,
            content="\n\n---\n\n".join(chunks),
        )


def _split_sections(body: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a markdown body into (preamble, [(h2-heading, section-body), ...]).

    The preamble is everything before the first ``##`` (typically the H1 title
    plus intro text) — callers must preserve it, not drop it.
    """
    parts = re.split(r"^##\s+(.+)$", body, flags=re.MULTILINE)
    preamble = parts[0]
    sections: list[tuple[str, str]] = []
    it = iter(parts[1:])
    for heading in it:
        sect_body = next(it, "")
        sections.append((heading.strip(), sect_body))
    return preamble, sections
