"""Regressions for the post-restart critical review (review pass 2).

Findings fixed here:
1. Distiller judge path bumped heat telemetry (machinery counted as usage).
2. TS/TSX ``../`` relative imports resolved to wrong dotted names.
3. ``scan`` traversed junk dirs fully before filtering (big-repo cost).
4. Over-relative python imports could underflow the package base.
5. Revision pass had no per-PROJECT lock (concurrent sessions could race).
6. Batched function summaries collided on bare names across modules.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tremula.astmap import FileMap, import_graph, map_file, resolve_import, scan
from tremula.bootstrap import plan_bootstrap, run_bootstrap
from tremula.config import Settings
from tremula.distiller import distill
from tremula.index import Index
from tremula.revise import (
    bump_and_maybe_revise,
    release_project_revise_lock,
    try_project_revise_lock,
)
from tremula.vault import VaultService

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_project"


@pytest.fixture
def vault_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_HOOKS_DISABLED", raising=False)
    vault_dir = tmp_path / "proj" / "tremula-vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "_index.md").write_text("---\ntype: index\nscope: shared\n---\n\n# P\n")
    mounts = {"proj": vault_dir}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    return VaultService(mounts, index, project="proj"), index, mounts


# ---- 1. judge path must not inflate heat -----------------------------------------

def test_distiller_collision_check_does_not_bump_heat(vault_setup):
    vault, index, _ = vault_setup
    uri = vault.write_note("Pinned", "# Pinned\n\nhuman text", type="decision")  # manual

    class Colliding:
        def complete(self, prompt: str) -> str:
            if "ENRICHMENT JUDGE" in prompt:
                return json.dumps({"decision": "reject", "reason": "redundant"})
            return json.dumps({"ops": [{"action": "write", "title": "Pinned",
                                        "type": "decision", "content": "thin"}]})

    distill([{"event": "Stop", "payload": {}}], vault, Colliding())
    assert index.get_meta(uri)["reads"] == 0  # machinery, not usage


# ---- 2 + 4. relative import resolution ----------------------------------------------

def test_ts_parent_relative_imports_resolve(tmp_path):
    (tmp_path / "web" / "components").mkdir(parents=True)
    (tmp_path / "web" / "client.ts").write_text("export const api = { base: '/api' };\n")
    (tmp_path / "web" / "components" / "deep.tsx").write_text(
        'import { api } from "../client";\n\n'
        "export function Deep() { return <div>{api.base}</div>; }\n"
    )
    files = [map_file(tmp_path, rel) for rel in scan(tmp_path)]
    graph = import_graph(files)
    assert graph["web.components.deep"] == ["web.client"]


def test_over_relative_imports_do_not_crash():
    importer = FileMap(path=Path("web/a.tsx"), language="tsx", dotted="web.a")
    assert resolve_import("../../nothing", importer, {}) is None  # beyond root -> None
    py = FileMap(path=Path("src/p/m.py"), language="python", dotted="p.m")
    assert resolve_import("....x", py, {"x": py}) == "x"  # underflow clamps to root


# ---- 3. scan prunes junk directories --------------------------------------------------

def test_scan_prunes_junk_and_keeps_lookalike_names(tmp_path):
    (tmp_path / "node_modules" / "pkg" / "src").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "src" / "x.ts").write_text("export const x = 1;\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "gen.py").write_text("x = 1\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "testing.py").write_text("# not a test file by our rules\nx = 1\n")
    rels = [str(p) for p in scan(tmp_path)]
    assert rels == ["src/testing.py"]  # junk pruned, lookalike kept


# ---- 5. per-project revision lock ------------------------------------------------------

def test_revision_skipped_while_project_lock_held(vault_setup, monkeypatch):
    vault, _, _ = vault_setup
    monkeypatch.setattr("tremula.revise.load_settings",
                        lambda: Settings(revision_every_n_runs=1))
    assert try_project_revise_lock("proj")  # simulate another session's pass
    try:
        assert bump_and_maybe_revise(vault, None) == []
    finally:
        release_project_revise_lock("proj")
    # lock free again -> the pass runs (n=1 -> fires immediately)
    log = bump_and_maybe_revise(vault, None)
    assert any("revision pass" in line for line in log)


# ---- 6. qualified function-summary keys win --------------------------------------------

def test_function_summaries_prefer_qualified_names(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    root = tmp_path / "sample_project"
    shutil.copytree(FIXTURE, root)
    vault_dir = root / "tremula-vault"
    vault_dir.mkdir()
    (vault_dir / "_index.md").write_text("---\ntype: index\nscope: shared\n---\n\n# S\n")
    mounts = {"sample": vault_dir}
    index = Index(tmp_path / "home" / "index" / "sample.sqlite")
    index.rebuild(mounts)
    vault = VaultService(mounts, index, project="sample")

    class QualifiedProvider:
        def complete(self, prompt: str) -> str:
            if prompt.startswith("MODULE SUMMARY"):
                return json.dumps({"purpose": "p", "public_api": []})
            if prompt.startswith("FUNCTION SUMMARIES"):
                return json.dumps({"functions": [
                    {"name": "samplepkg.auth.login", "summary": "QUALIFIED WINS"},
                    {"name": "login", "summary": "bare must lose"},
                ]})
            return '{"ops": []}'

    run_bootstrap(vault, QualifiedProvider(), plan_bootstrap(root), Settings())
    note = vault.read_note("memory://sample/functions/samplepkg-auth-login", track=False)
    assert "QUALIFIED WINS" in note["body"]
