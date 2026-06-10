"""Stage 1 acceptance: notes in the seeded vault parse and validate."""

from pathlib import Path

import pytest

from tremula.note import (
    Note,
    NoteType,
    Scope,
    load_note_in_vault,
)

VAULT = Path(__file__).resolve().parent.parent / "tremula-vault"


def _all_notes():
    return sorted(VAULT.rglob("*.md"))


def test_vault_has_seed_notes():
    paths = {p.relative_to(VAULT).as_posix() for p in _all_notes()}
    assert "_index.md" in paths
    assert "decisions/name-tremula.md" in paths
    assert "conventions/frontmatter-schema.md" in paths


@pytest.mark.parametrize("path", _all_notes(), ids=lambda p: p.name)
def test_every_seed_note_parses(path):
    note = load_note_in_vault(path, VAULT, project="tremula")
    assert isinstance(note, Note)
    assert isinstance(note.frontmatter.type, NoteType)
    assert isinstance(note.frontmatter.scope, Scope)
    assert note.title  # non-empty


def test_typed_links_become_memory_uris():
    note = load_note_in_vault(
        VAULT / "conventions/memory-uri-addressing.md", VAULT, project="tremula"
    )
    uris = note.linked_uris()
    assert any(u.path == "decisions/vault-at-repo-root" for u in uris)


def test_uri_derived_from_path():
    note = load_note_in_vault(
        VAULT / "decisions/stdio-transport.md", VAULT, project="tremula"
    )
    assert str(note.uri) == "memory://tremula/decisions/stdio-transport"
