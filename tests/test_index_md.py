"""Auto-section sync in _index.md: new note files surface mechanically;
human-curated content is never touched; endorsement (moving a link up) sticks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tremula import hooks
from tremula.distiller import run_distill
from tremula.index import Index
from tremula.index_md import AUTO_BEGIN, AUTO_END, sync_index_auto_section
from tremula.registry import SessionContext
from tremula.vault import VaultService

MANUAL = """---
type: index
scope: shared
---

# Proj Index

curated intro text

## Decisions
- [[decisions/endorsed]] — already curated
"""


def _note(path: Path, title: str, type_: str = "decision", source: str = "manual"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntype: {type_}\nscope: shared\nsource: {source}\n---\n\n# {title}\n\nbody\n"
    )


@pytest.fixture
def vault_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_HOOKS_DISABLED", raising=False)
    vault = tmp_path / "proj" / "tremula-vault"
    vault.mkdir(parents=True)
    (vault / "_index.md").write_text(MANUAL)
    _note(vault / "decisions" / "endorsed.md", "Endorsed decision")
    return vault


def test_unlinked_note_appears_linked_note_does_not(vault_dir):
    _note(vault_dir / "decisions" / "fresh.md", "Fresh decision", source="distilled")
    assert sync_index_auto_section(vault_dir, "proj") is True
    text = (vault_dir / "_index.md").read_text()
    auto = text.split(AUTO_BEGIN)[1].split(AUTO_END)[0]
    assert "[[decisions/fresh]]" in auto
    assert "Fresh decision" in auto and "distilled" in auto
    assert "[[decisions/endorsed]]" not in auto  # already curated above


def test_manual_content_untouched_and_idempotent(vault_dir):
    _note(vault_dir / "decisions" / "fresh.md", "Fresh decision")
    sync_index_auto_section(vault_dir, "proj")
    text1 = (vault_dir / "_index.md").read_text()
    assert "curated intro text" in text1
    assert "## Decisions\n- [[decisions/endorsed]] — already curated" in text1
    # second sync with no changes: no rewrite
    assert sync_index_auto_section(vault_dir, "proj") is False
    assert (vault_dir / "_index.md").read_text() == text1


def test_endorsing_moves_note_out_of_auto_section(vault_dir):
    _note(vault_dir / "decisions" / "fresh.md", "Fresh decision")
    sync_index_auto_section(vault_dir, "proj")
    text = (vault_dir / "_index.md").read_text()
    # human endorses: add the link to the curated part (above the markers)
    text = text.replace("- [[decisions/endorsed]] — already curated",
                        "- [[decisions/endorsed]] — already curated\n"
                        "- [[decisions/fresh]] — endorsed now")
    (vault_dir / "_index.md").write_text(text)
    assert sync_index_auto_section(vault_dir, "proj") is True
    auto = (vault_dir / "_index.md").read_text().split(AUTO_BEGIN)[1].split(AUTO_END)[0]
    assert "[[decisions/fresh]]" not in auto  # graduated out of the auto list


def test_memory_uri_reference_counts_as_linked(vault_dir):
    _note(vault_dir / "modules" / "engine.md", "Engine")
    text = (vault_dir / "_index.md").read_text().replace(
        "## Decisions", "- memory://proj/modules/engine — engine\n\n## Decisions")
    (vault_dir / "_index.md").write_text(text)
    sync_index_auto_section(vault_dir, "proj")
    auto = (vault_dir / "_index.md").read_text().split(AUTO_BEGIN)[1].split(AUTO_END)[0]
    assert "engine" not in auto


def test_sessionstart_syncs_auto_section(vault_dir, monkeypatch, capsys):
    _note(vault_dir / "conventions" / "dropped-in.md", "Dropped in by hand")
    mounts = {"proj": vault_dir}
    monkeypatch.setattr(hooks, "resolve_session",
                        lambda **k: SessionContext(project="proj", mounts=mounts,
                                                   registry_path=vault_dir))
    assert hooks.run_hook("SessionStart", {"session_id": "s",
                                           "cwd": str(vault_dir.parent)}) == 0
    text = (vault_dir / "_index.md").read_text()
    assert "[[conventions/dropped-in]]" in text
    # and the injected block already contains the auto-listed note
    assert "Dropped in by hand" in capsys.readouterr().out


def test_distill_run_syncs_auto_section(vault_dir, tmp_path):
    mounts = {"proj": vault_dir}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    vault = VaultService(mounts, index, project="proj")

    class P:
        def complete(self, prompt: str) -> str:
            return json.dumps({"ops": [{"action": "write", "title": "From session",
                                        "type": "decision", "content": "captured"}]})

    session = tmp_path / "s.ndjson"
    session.write_text(json.dumps({"ts": 1.0, "event": "Stop", "payload": {}}) + "\n")
    applied = run_distill(str(session), vault, P(), trigger="SessionEnd")
    assert any(line.startswith("write ") for line in applied)
    assert "[[decisions/from-session]]" in (vault_dir / "_index.md").read_text()


def test_missing_index_is_noop(tmp_path):
    empty = tmp_path / "vault"
    empty.mkdir()
    assert sync_index_auto_section(empty, "proj") is False
