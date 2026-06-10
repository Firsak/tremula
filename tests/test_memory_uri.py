"""Stage 1 acceptance: memory:// URIs parse and resolve within a mount set."""

from pathlib import Path

import pytest

from tremula.memory_uri import (
    MemoryURI,
    MemoryURIError,
    is_memory_uri,
    resolve,
)


def test_parse_basic():
    uri = MemoryURI.parse("memory://tremula/decisions/name-tremula")
    assert uri.project == "tremula"
    assert uri.path == "decisions/name-tremula"
    assert uri.note_id == "name-tremula"
    assert str(uri) == "memory://tremula/decisions/name-tremula"


def test_parse_strips_md_suffix():
    uri = MemoryURI.parse("memory://api/modules/auth.md")
    assert uri.path == "modules/auth"
    assert uri.relative_file() == Path("modules/auth.md")


@pytest.mark.parametrize(
    "bad",
    [
        "decisions/name",            # no scheme
        "memory://tremula",          # no note path
        "memory:///decisions/name",  # empty project
        "https://x/y",               # wrong scheme
    ],
)
def test_parse_rejects_invalid(bad):
    assert not is_memory_uri(bad)
    with pytest.raises(MemoryURIError):
        MemoryURI.parse(bad)


def test_resolve_within_mount_set(tmp_path):
    roots = {"tremula": tmp_path / "tremula-vault"}
    resolved = resolve("memory://tremula/decisions/name-tremula", roots)
    assert resolved == (tmp_path / "tremula-vault/decisions/name-tremula.md").resolve()


def test_resolve_outside_mount_set_raises():
    roots = {"tremula": Path("/tmp/tremula-vault")}
    with pytest.raises(MemoryURIError, match="not in the mount set"):
        resolve("memory://api/modules/auth", roots)
