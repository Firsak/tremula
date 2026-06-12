"""CLI-level tests: the commands a user actually types, run through main(argv).

Everything is isolated under a temp TREMULA_HOME (which, after the review fix,
also anchors the default registry path).
"""

from __future__ import annotations

import pytest

from tremula.cli import main
from tremula.hooks import run_hook


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An isolated repo with a seeded vault, cwd inside it, temp TREMULA_HOME."""
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    monkeypatch.delenv("TREMULA_HOOKS_DISABLED", raising=False)
    repo = tmp_path / "myproj"
    vault = repo / "tremula-vault"
    vault.mkdir(parents=True)
    (vault / "_index.md").write_text(
        "---\ntype: index\nscope: shared\n---\n\n# MyProj Index\n\nhello index\n"
    )
    (vault / "decisions").mkdir()
    (vault / "decisions" / "a.md").write_text(
        "---\ntype: decision\nscope: shared\n---\n\n# Decision A\n\nbody\n"
    )
    monkeypatch.chdir(repo)
    return repo


def test_registry_init_then_show_and_vault(project, capsys):
    assert main(["registry", "init", "--name", "myproj"]) == 0
    out = capsys.readouterr().out
    assert "registered 'myproj'" in out

    assert main(["registry"]) == 0
    out = capsys.readouterr().out
    assert "myproj" in out and "memory://myproj/" in out

    assert main(["vault"]) == 0
    out = capsys.readouterr().out
    assert "via registry" in out
    assert "memory://myproj/decisions/a" in out


def test_registry_init_creates_vault_when_absent(tmp_path, monkeypatch, capsys):
    """init bootstraps tremula-vault/ so init -> bootstrap doesn't deadlock."""
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    repo = tmp_path / "fresh"
    repo.mkdir()
    monkeypatch.chdir(repo)

    assert not (repo / "tremula-vault").exists()
    assert main(["registry", "init"]) == 0
    out = capsys.readouterr().out
    assert "created vault" in out
    assert (repo / "tremula-vault" / "_index.md").is_file()
    # cwd now resolves to a registered project -> bootstrap is unblocked.
    assert main(["registry"]) == 0
    assert "fresh" in capsys.readouterr().out


def test_registry_init_self_heals_vault_missing_index(tmp_path, monkeypatch, capsys):
    """A vault dir that exists but has no _index.md (made by hand / old init) gets
    one on `registry init` — not only on fresh creation."""
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    repo = tmp_path / "handmade"
    vault = repo / "tremula-vault"
    vault.mkdir(parents=True)  # vault exists, but NO _index.md
    monkeypatch.chdir(repo)

    assert not (vault / "_index.md").exists()
    assert main(["registry", "init"]) == 0
    assert (vault / "_index.md").is_file()
    assert "created" in capsys.readouterr().out


def test_registry_init_no_create_still_requires_vault(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    repo = tmp_path / "fresh2"
    repo.mkdir()
    monkeypatch.chdir(repo)
    assert main(["registry", "init", "--no-create"]) == 1
    assert "no tremula-vault/" in capsys.readouterr().err
    assert not (repo / "tremula-vault").exists()


def test_registry_init_refuses_overwrite_without_force(project, capsys):
    assert main(["registry", "init", "--name", "myproj"]) == 0
    capsys.readouterr()
    assert main(["registry", "init", "--name", "myproj"]) == 1
    assert "already registered" in capsys.readouterr().err
    assert main(["registry", "init", "--name", "myproj", "--force"]) == 0


def test_index_rebuild_counts_notes(project, capsys):
    main(["registry", "init", "--name", "myproj"])
    capsys.readouterr()
    assert main(["index", "rebuild"]) == 0
    assert "indexed 2 notes" in capsys.readouterr().out


def test_vault_outside_any_project_fails_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["vault"]) == 1
    assert "no project" in capsys.readouterr().err


def test_hook_sessionstart_prints_injection_without_frontmatter(project, capsys):
    main(["registry", "init", "--name", "myproj"])
    capsys.readouterr()
    rc = run_hook("SessionStart", {"session_id": "s1", "cwd": str(project)})
    out = capsys.readouterr().out
    assert rc == 0
    assert "MyProj Index" in out
    assert "type: index" not in out  # frontmatter stripped from injection


def test_hook_capture_writes_clipped_ndjson(project, capsys):
    main(["registry", "init", "--name", "myproj"])
    capsys.readouterr()
    rc = run_hook("PostToolUse", {"session_id": "s2", "cwd": str(project),
                                  "tool_response": "z" * 50_000})
    assert rc == 0
    from tremula.capture import read_session, session_file
    events = read_session(session_file("myproj", "s2"))
    assert len(events) == 1
    assert "…[+" in events[0]["payload"]["tool_response"]


def test_hook_for_unregistered_cwd_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    assert run_hook("Stop", {"session_id": "x", "cwd": str(tmp_path)}) == 0
