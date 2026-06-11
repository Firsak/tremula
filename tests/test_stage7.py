"""Stage 7 acceptance: heat telemetry, oversized auto-split, judged duplicate
merge with link rewiring, stale archiving to attic/, revision trigger, CLI."""

from __future__ import annotations

import json
import os
import time

import pytest

from tremula.config import Settings
from tremula.distiller import run_distill
from tremula.index import Index
from tremula.index_md import sync_index_auto_section
from tremula.revise import (
    archive_note,
    find_duplicate_candidates,
    find_stale,
    revise,
    rewrite_inbound_links,
)
from tremula.vault import VaultService

NOW = time.time()
OLD = NOW - 30 * 86400  # 30 days ago


@pytest.fixture
def vault_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_HOOKS_DISABLED", raising=False)
    vault_dir = tmp_path / "proj" / "tremula-vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "_index.md").write_text(
        "---\ntype: index\nscope: shared\n---\n\n# Proj\n"
    )
    mounts = {"proj": vault_dir}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    return VaultService(mounts, index, project="proj"), index, mounts


def _age(mounts, rel: str, when: float = OLD) -> None:
    path = mounts["proj"] / rel
    os.utime(path, (when, when))


class Scripted:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


# ---- heat telemetry ---------------------------------------------------------------

def test_reads_bump_and_machinery_does_not(vault_setup):
    vault, index, _ = vault_setup
    uri = vault.write_note("Hot one", "body", type="module")
    vault.read_note(uri)
    vault.read_note(uri)
    assert index.get_meta(uri)["reads"] == 2
    vault.existing_notes()  # distiller snapshot: must NOT count as usage
    assert index.get_meta(uri)["reads"] == 2


def test_heat_survives_rewrite_and_rebuild(vault_setup):
    vault, index, mounts = vault_setup
    uri = vault.write_note("Warm", "v1", type="module")
    vault.read_note(uri)
    vault.write_note("Warm", "v2 rewritten", type="module")  # upsert
    assert index.get_meta(uri)["reads"] == 1
    index.rebuild(mounts)
    assert index.get_meta(uri)["reads"] == 1


# ---- attic ---------------------------------------------------------------------------

def test_archive_moves_to_attic_and_leaves_active_graph(vault_setup):
    vault, index, mounts = vault_setup
    uri = vault.write_note("Cold thing", "rarely useful text", type="module",
                           source="distilled")
    target = archive_note(vault, uri, reason="test")
    assert target.exists() and "attic" in target.parts
    assert "archived" in target.read_text()
    assert vault.search("rarely useful") == []          # not searchable
    index.rebuild(mounts)
    assert index.get_meta(uri) is None                  # rebuild skips attic
    sync_index_auto_section(mounts["proj"], "proj")
    assert "Cold thing" not in (mounts["proj"] / "_index.md").read_text()


# ---- oversized -------------------------------------------------------------------------

def test_oversized_distilled_splits_manual_only_suggested(vault_setup):
    vault, _, _ = vault_setup
    big_body = "# Big\n\nintro\n\n## A\n\n" + "x " * 200 + "\n\n## B\n\n" + "y " * 200
    vault.write_note("Big", big_body, type="architecture", source="distilled")
    vault.write_note("Manual big", big_body.replace("Big", "Manual big"),
                     type="architecture")  # manual
    settings = Settings(max_note_chars=300)
    log = revise(vault, None, settings)
    assert any(line.startswith("split memory://proj/architecture/big") for line in log)
    assert vault.read_note("memory://proj/architecture/big-a", track=False)  # child
    assert any("suggest split" in line and "manual-big" in line for line in log)
    # manual note untouched
    manual = vault.read_note("memory://proj/architecture/manual-big", track=False)
    assert "## A" in manual["body"]


# ---- duplicates ---------------------------------------------------------------------------

def _dup_pair(vault):
    a = vault.write_note("tremula.workctx", "# tremula.workctx\n\nExtracts working "
                         "context from session events and git status.",
                         type="module", source="distilled")
    b = vault.write_note("Module: workctx — working-context extraction",
                         "# Module: workctx\n\nWorking-context extraction for the "
                         "retrieval funnel: paths, terms, git status.",
                         type="module", source="distilled")
    return a, b


def test_duplicate_candidates_catch_the_workctx_case(vault_setup):
    vault, _, _ = vault_setup
    a, b = _dup_pair(vault)
    pairs = find_duplicate_candidates(vault)
    assert {(x["uri"], y["uri"]) for x, y in pairs} & {(a, b), (b, a)}


def test_shared_package_prefix_is_not_duplication(vault_setup):
    """Regression (live dogfood): every tremula.* module paired with every
    other because they share the ubiquitous 'tremula' title token."""
    vault, _, _ = vault_setup
    for stem in ("cli", "bootstrap", "server", "config", "capture", "registry",
                 "injection", "workctx", "index_md", "revise"):
        vault.write_note(f"tremula.{stem}", f"# tremula.{stem}\n\nmodule {stem}",
                         type="module", source="distilled")
    # sibling FUNCTIONS of one module share the module segment — also not dups
    for fn in ("hooks_disabled", "sessions_dir", "index_path"):
        vault.write_note(f"tremula.config.{fn}", f"# tremula.config.{fn}\n\nfn",
                         type="function", source="distilled")
    assert find_duplicate_candidates(vault) == []


def test_merge_end_to_end_with_link_rewiring(vault_setup):
    vault, _, mounts = vault_setup
    a, b = _dup_pair(vault)
    # referrer links to b -> b is better-anchored -> b survives (inbound links
    # outrank heat by design: the better-wired note keeps its URI)
    referrer = vault.write_note("Referrer", "uses workctx", type="module",
                                links={"depends_on": [b]})
    vault.read_note(a, track=True)  # heat alone must NOT outrank inbound links
    merged = ("# Module: workctx\n\nExtracts working context from session events "
              "and git status. Working-context extraction for the retrieval "
              "funnel: paths, terms, tremula.workctx.")
    provider = Scripted(json.dumps({"merge": True, "content": merged, "reason": "same"}))
    log = revise(vault, provider, Settings())
    assert any(line.startswith(f"merge {a} -> {b}") for line in log)
    assert "session events" in vault.read_note(b, track=False)["body"]
    # loser archived; referrer still points at the surviving URI
    assert b in vault.read_note(referrer, track=False)["links"]["depends_on"]
    assert (mounts["proj"] / "attic" / "modules").exists()
    with pytest.raises(FileNotFoundError):
        vault.read_note(a, track=False)


def test_merge_rejected_or_lossy_keeps_both(vault_setup):
    vault, _, _ = vault_setup
    a, b = _dup_pair(vault)
    log = revise(vault, Scripted(json.dumps({"merge": False, "reason": "different"})),
                 Settings())
    assert any(line.startswith("keep both") for line in log)
    # lossy merged body (drops nearly everything) -> backstop blocks
    log = revise(vault, Scripted(json.dumps({"merge": True, "content": "# x\n\nstub",
                                             "reason": "looks fine"})), Settings())
    assert any("backstop blocked" in line for line in log)
    assert vault.read_note(a, track=False) and vault.read_note(b, track=False)


# ---- stale -----------------------------------------------------------------------------

def test_stale_requires_cold_old_unlinked_distilled(vault_setup):
    vault, _, mounts = vault_setup
    cold = vault.write_note("Cold note", "never used", type="module", source="distilled")
    warm = vault.write_note("Warm note", "gets read", type="module", source="distilled")
    linked = vault.write_note("Linked note", "referenced", type="module", source="distilled")
    vault.write_note("Refers", "points", type="module", links={"depends_on": [linked]})
    manual_cold = vault.write_note("Manual cold", "old manual", type="decision")
    for rel in ("modules/cold-note.md", "modules/warm-note.md",
                "modules/linked-note.md", "decisions/manual-cold.md"):
        _age(mounts, rel)
    vault.index.refresh(mounts)
    vault.read_note(warm)  # warm has heat
    uris = {n["uri"] for n in find_stale(vault, NOW, stale_after_days=14)}
    assert cold in uris
    assert warm not in uris and linked not in uris and manual_cold not in uris


def test_stale_archived_only_when_confirmed(vault_setup):
    vault, _, mounts = vault_setup
    cold1 = vault.write_note("Cold a", "unused a", type="module", source="distilled")
    cold2 = vault.write_note("Cold b", "unused b", type="module", source="distilled")
    _age(mounts, "modules/cold-a.md")
    _age(mounts, "modules/cold-b.md")
    vault.index.refresh(mounts)
    provider = Scripted(json.dumps({"archive": [cold1], "reason": "obsolete"}))
    log = revise(vault, provider, Settings(), now=NOW)
    assert any(line == f"archive {cold1}" for line in log)
    assert any(line.startswith(f"keep {cold2}") for line in log)
    with pytest.raises(FileNotFoundError):
        vault.read_note(cold1, track=False)
    assert vault.read_note(cold2, track=False)


# ---- trigger + CLI -------------------------------------------------------------------------

def test_every_nth_distill_run_triggers_revision(vault_setup, tmp_path, monkeypatch):
    vault, _, _ = vault_setup
    monkeypatch.setattr("tremula.revise.load_settings",
                        lambda: Settings(revision_every_n_runs=2))
    provider = Scripted('{"ops": []}')
    session = tmp_path / "s.ndjson"
    for i in range(2):
        prev = session.read_text() if session.exists() else ""
        session.write_text(prev + json.dumps({"ts": float(i), "event": "Stop",
                                              "payload": {"n": i}}) + "\n")
        log = run_distill(str(session), vault, provider, trigger="SessionEnd")
    assert any("revision pass" in line for line in log)  # fired on run 2


def test_rewrite_inbound_links_unit(vault_setup):
    vault, _, _ = vault_setup
    old = vault.write_note("Old target", "x", type="module", source="distilled")
    new = vault.write_note("New target", "y", type="module", source="distilled")
    src = vault.write_note("Source", "links out", type="module",
                           links={"depends_on": [old], "implements": [old]})
    assert rewrite_inbound_links(vault, old, new) == 1
    note = vault.read_note(src, track=False)
    assert note["links"]["depends_on"] == [new]
    assert note["links"]["implements"] == [new]


def test_cli_revise_dry_run(vault_setup, monkeypatch, capsys):
    from tremula.cli import main

    _, _, mounts = vault_setup
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    monkeypatch.chdir(mounts["proj"].parent)
    main(["registry", "init", "--name", "proj"])
    capsys.readouterr()
    assert main(["revise", "--dry-run"]) == 0
    assert "revision pass (dry-run)" in capsys.readouterr().out
