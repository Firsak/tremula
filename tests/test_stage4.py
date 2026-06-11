"""Stage 4 acceptance: working-context extraction, OR-search, index refresh,
proactive attach with dedupe sidecar, sidecar reset on SessionStart,
cross-root get_context, distill.log."""

from __future__ import annotations

import subprocess

import pytest

from tremula import hooks
from tremula.capture import append_event, session_file
from tremula.config import Settings
from tremula.index import Index
from tremula.injection import (
    build_attachment,
    injected_path,
    load_injected,
    record_injected,
    save_injected,
)
from tremula.registry import SessionContext
from tremula.vault import VaultService
from tremula.workctx import (
    derive_terms,
    extract_paths_from_events,
    git_changed_files,
    working_context,
)


@pytest.fixture
def vault_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_HOOKS_DISABLED", raising=False)
    vault_dir = tmp_path / "proj" / "tremula-vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "_index.md").write_text(
        "---\ntype: index\nscope: shared\n---\n\n# Proj Index\n\nentry\n"
    )
    mounts = {"proj": vault_dir}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    return VaultService(mounts, index, project="proj"), index, mounts


# ---- working-context extraction ------------------------------------------------

def _evt(file_path: str) -> dict:
    return {"event": "PostToolUse",
            "payload": {"tool_name": "Edit", "tool_input": {"file_path": file_path}}}


def test_extract_paths_newest_first_distinct():
    events = [_evt("src/a.py"), _evt("src/b.py"), _evt("src/a.py"),
              {"event": "UserPromptSubmit", "payload": {"text": "no paths here"}}]
    paths = extract_paths_from_events(events, max_paths=5)
    assert paths[0] == "src/a.py"  # most recent occurrence wins the front
    assert paths == ["src/a.py", "src/b.py"]


def test_extract_paths_nested_keys():
    events = [{"event": "PostToolUse",
               "payload": {"tool_response": {"results": [{"path": "lib/deep/thing.ts"}]}}}]
    assert extract_paths_from_events(events) == ["lib/deep/thing.ts"]


def test_derive_terms_stems_and_stopwords():
    terms = derive_terms(["src/tremula/memory_uri.py", "tests/test_vault.py"])
    assert "memory" in terms and "uri" in terms and "tremula" in terms
    assert "vault" in terms
    assert "src" not in terms and "tests" not in terms and "py" not in terms


def test_git_changed_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "tracked.py").write_text("x = 1\n")
    assert "tracked.py" in git_changed_files(repo)
    assert git_changed_files(tmp_path / "not-a-repo") == []


def test_working_context_combines_session_and_git(tmp_path, vault_setup):
    append_event("proj", "wc", "PostToolUse",
                 {"tool_input": {"file_path": "src/distiller_core.py"}})
    ctx = working_context(session_file("proj", "wc"), repo_root=None)
    assert "distiller" in ctx["terms"] and "core" in ctx["terms"]


# ---- OR search ------------------------------------------------------------------

def test_search_any_matches_any_term(vault_setup):
    vault, index, _ = vault_setup
    a = vault.write_note("Vault engine", "write path and index", type="module")
    vault.write_note("Unrelated", "completely different topic", type="module")
    hits = index.search_any(["vault", "zzznothing"])
    assert [h.uri for h in hits][:1] == [a]
    assert index.search_any([]) == []
    assert isinstance(index.search_any(['weird "(((']), list)  # never crashes


# ---- index refresh (pull-based consistency) ---------------------------------------

def test_refresh_sees_manual_edit_without_rebuild(vault_setup):
    vault, index, mounts = vault_setup
    uri = vault.write_note("Live note", "original wording alpha", type="module")
    path = mounts["proj"] / "modules" / "live-note.md"
    # simulate a human editing the file directly (different size => detected)
    path.write_text(path.read_text().replace("alpha", "freshly-edited-zebra-content"))
    hits = vault.search("zebra")
    assert hits and hits[0]["uri"] == uri


def test_refresh_sees_new_and_deleted_files(vault_setup):
    vault, index, mounts = vault_setup
    new = mounts["proj"] / "decisions" / "outside.md"
    new.parent.mkdir(exist_ok=True)
    new.write_text("---\ntype: decision\nscope: shared\n---\n\n# Outside\n\nmade externally\n")
    assert any(h["uri"].endswith("outside") for h in vault.search("externally"))
    new.unlink()
    assert not any(h["uri"].endswith("outside") for h in vault.search("externally"))


# ---- proactive attach --------------------------------------------------------------

def test_attach_by_working_context_not_prompt(vault_setup):
    vault, _, _ = vault_setup
    uri = vault.write_note("Vault engine", "how the vault write path works", type="module")
    block, attached = build_attachment(vault, ["vault"], exclude=set(), settings=Settings())
    assert attached == [uri]
    assert "Vault engine" in block and uri in block


def test_attach_dedupes_and_skips_index(vault_setup):
    vault, _, _ = vault_setup
    uri = vault.write_note("Vault engine", "vault internals", type="module")
    block, attached = build_attachment(vault, ["vault"], exclude={uri}, settings=Settings())
    assert attached == [] and block == ""  # already injected -> silence
    # _index never attaches even when it matches
    block, attached = build_attachment(vault, ["proj", "index", "entry"],
                                       exclude=set(), settings=Settings())
    assert all(not u.endswith("/_index") for u in attached)


def test_attach_respects_caps(vault_setup):
    vault, _, _ = vault_setup
    for i in range(6):
        vault.write_note(f"Vault part {i}", "vault " * 120, type="module")
    settings = Settings()
    block, attached = build_attachment(vault, ["vault"], exclude=set(), settings=settings)
    assert 0 < len(attached) <= settings.attach_notes
    assert len(block) <= settings.attach_max_chars + 60  # header allowance


def test_attach_silent_without_terms(vault_setup):
    vault, _, _ = vault_setup
    assert build_attachment(vault, [], exclude=set(), settings=Settings()) == ("", [])


# ---- sidecar lifecycle ----------------------------------------------------------------

def test_sidecar_roundtrip_and_corrupt_tolerance(tmp_path):
    session = tmp_path / "s.ndjson"
    record_injected(session, ["memory://p/a"])
    record_injected(session, ["memory://p/b", "memory://p/a"])
    assert load_injected(session) == {"memory://p/a", "memory://p/b"}
    injected_path(session).write_text("{corrupt!!")
    assert load_injected(session) == set()  # tolerant, never raises


def test_sessionstart_resets_sidecar_making_notes_reattachable(vault_setup, monkeypatch, capsys):
    vault, index, mounts = vault_setup
    uri = vault.write_note("Vault engine", "vault internals", type="module")
    session = session_file("proj", "sess-compact")
    save_injected(session, [uri, "memory://p/stale"])  # pre-compact state

    monkeypatch.setattr(hooks, "resolve_session",
                        lambda **k: SessionContext(project="proj", mounts=mounts,
                                                   registry_path=mounts["proj"]))
    rc = hooks.run_hook("SessionStart", {"session_id": "sess-compact",
                                         "cwd": str(mounts["proj"].parent)})
    assert rc == 0
    injected = load_injected(session)
    assert "memory://p/stale" not in injected      # reset happened
    # the previously attached note is attachable again (only fresh injections excluded)
    block, attached = build_attachment(vault, ["vault"], exclude=injected,
                                       settings=Settings())
    assert uri in attached or uri in injected  # re-attachable unless it was just re-injected


def test_userpromptsubmit_attaches_and_captures(vault_setup, monkeypatch, capsys):
    vault, index, mounts = vault_setup
    uri = vault.write_note("Distiller core", "incremental offsets and locks", type="module")
    monkeypatch.setattr(hooks, "resolve_session",
                        lambda **k: SessionContext(project="proj", mounts=mounts,
                                                   registry_path=mounts["proj"]))
    payload = {"session_id": "upx", "cwd": str(mounts["proj"].parent),
               "tool_input": {"file_path": "src/distiller_core.py"}}
    # first prompt records the file-touching event
    assert hooks.run_hook("UserPromptSubmit", payload) == 0
    out1 = capsys.readouterr().out
    # second prompt: working context (from captured events) finds the note
    assert hooks.run_hook("UserPromptSubmit",
                          {"session_id": "upx", "cwd": str(mounts["proj"].parent)}) == 0
    out2 = capsys.readouterr().out
    assert "Distiller core" in (out1 + out2)
    assert uri in load_injected(session_file("proj", "upx"))
    # third prompt: deduped -> silent
    assert hooks.run_hook("UserPromptSubmit",
                          {"session_id": "upx", "cwd": str(mounts["proj"].parent)}) == 0
    assert "Distiller core" not in capsys.readouterr().out


# ---- get_context crosses into a root vault ----------------------------------------

def test_get_context_crosses_root_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    ramet = tmp_path / "proj" / "tremula-vault"
    root = tmp_path / "roots" / "proj-api"
    (ramet / "modules").mkdir(parents=True)
    (root / "contracts").mkdir(parents=True)
    (root / "contracts" / "post-items.md").write_text(
        "---\ntype: contract\nscope: shared\n---\n\n# POST /items contract\n\nshared schema\n"
    )
    (ramet / "modules" / "client.md").write_text(
        "---\ntype: module\nscope: shared\n"
        "implements: [memory://proj-api/contracts/post-items]\n---\n\n"
        "# Items client\n\ncalls the items endpoint\n"
    )
    mounts = {"proj": ramet, "proj-api": root}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    vault = VaultService(mounts, index, project="proj")

    result = vault.get_context("items endpoint client", depth=1)
    assert any(u.startswith("memory://proj-api/") for u in result.neighbors)
    assert "POST /items contract" in result.content  # crossed the vault boundary


# ---- distiller logging ---------------------------------------------------------------

def test_spawn_distiller_logs_stderr_to_file(vault_setup, monkeypatch, tmp_path):
    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["stderr"] = kwargs.get("stderr")

        class FakeProc:
            pid = 1

        return FakeProc()

    monkeypatch.setattr(hooks.subprocess, "Popen", fake_popen)
    hooks._spawn_distiller(tmp_path / "s.ndjson", "proj", trigger="Stop")
    assert captured["stderr"] is not None
    assert captured["stderr"].name.endswith("distill.log")
