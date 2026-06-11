"""Stage 5 acceptance: scan/AST map, import graph, bootstrap pipeline with a
fake provider, idempotent re-run, manual-note protection, roots draft, dry-run."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tremula.astmap import dotted_name, import_graph, map_file, scan
from tremula.bootstrap import plan_bootstrap, run_bootstrap
from tremula.config import Settings
from tremula.index import Index
from tremula.registry import Registry
from tremula.vault import VaultService

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_project"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway copy of the fixture repo with vault + index wired."""
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    root = tmp_path / "sample_project"
    shutil.copytree(FIXTURE, root)
    vault_dir = root / "tremula-vault"
    vault_dir.mkdir()
    (vault_dir / "_index.md").write_text(
        "---\ntype: index\nscope: shared\n---\n\n# Sample Index\n"
    )
    mounts = {"sample": vault_dir}
    index = Index(tmp_path / "home" / "index" / "sample.sqlite")
    index.rebuild(mounts)
    return root, VaultService(mounts, index, project="sample"), mounts


class BootstrapFake:
    """Scripted provider answering each prompt kind with canned JSON."""

    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if prompt.startswith("MODULE SUMMARY"):
            dotted = prompt.split("MODULE: ", 1)[1].split(" ", 1)[0]
            return json.dumps({"purpose": f"Handles {dotted} duties.",
                               "public_api": [{"signature": "f()", "description": "does f"}]})
        if prompt.startswith("FUNCTION SUMMARIES"):
            return json.dumps({"functions": [
                {"name": "login", "summary": "Logs a user in and stores a token."},
                {"name": "save_token", "summary": "Persists a token."},
            ]})
        if prompt.startswith("CONVENTIONS PASS"):
            return json.dumps({"ops": [{"action": "write", "title": "Ruff line length",
                                        "type": "convention", "scope": "shared",
                                        "content": "Line length is 88 (ruff)."}]})
        return '{"ops": []}'


# ---- scan + AST map -------------------------------------------------------------

def test_scan_filters_junk_and_tests():
    rels = [str(p) for p in scan(FIXTURE)]
    assert "src/samplepkg/auth.py" in rels
    assert "web/button.tsx" in rels
    assert not any("node_modules" in r for r in rels)
    assert not any(r.startswith("tests/") for r in rels)


def test_python_astmap_symbols_exports_imports():
    fmap = map_file(FIXTURE, Path("src/samplepkg/auth.py"))
    names = {s.name: s for s in fmap.symbols}
    assert names["login"].exported and names["logout"].exported
    assert not names["_helper"].exported
    assert ".store" in fmap.imports
    assert fmap.dotted == "samplepkg.auth"


def test_tsx_astmap_exports():
    fmap = map_file(FIXTURE, Path("web/button.tsx"))
    names = {s.name: s for s in fmap.symbols}
    assert names["Button"].exported
    assert not names["internalHelper"].exported
    assert "./client" in fmap.imports
    assert fmap.dotted == "web.button"


def test_dotted_name_rules():
    assert dotted_name(Path("src/tremula/vault.py")) == "tremula.vault"
    assert dotted_name(Path("src/samplepkg/__init__.py")) == "samplepkg"
    assert dotted_name(Path("web/client.ts")) == "web.client"


def test_import_graph_resolves_relative_imports():
    files = [map_file(FIXTURE, rel) for rel in scan(FIXTURE)]
    graph = import_graph(files)
    assert "samplepkg.store" in graph["samplepkg.auth"]
    assert "web.client" in graph["web.button"]
    assert graph["samplepkg.store"] == []  # imports nothing internal


# ---- planning -------------------------------------------------------------------

def test_plan_selects_referenced_exported_functions():
    plan = plan_bootstrap(FIXTURE)
    selected = {name for _, name, _ in plan.functions}
    assert "login" in selected          # exported top-level fn, referenced from __init__
    assert "_helper" not in selected    # not exported
    assert "save_token" not in selected  # class METHOD: v1 maps top-level functions only
    assert "push_items" not in selected  # exported but referenced nowhere
    assert ("samplepkg.api_client", "https://api.example.com/items") in plan.external_calls


def test_dry_run_makes_zero_llm_calls(repo):
    root, vault, _ = repo
    provider = BootstrapFake()
    log = run_bootstrap(vault, provider, plan_bootstrap(root), Settings(), dry_run=True)
    assert provider.calls == 0
    assert any("dry-run" in line for line in log)
    assert vault.search("duties") == []  # nothing written


# ---- full run --------------------------------------------------------------------

def test_bootstrap_populates_linked_vault(repo):
    root, vault, mounts = repo
    plan = plan_bootstrap(root)
    log = run_bootstrap(vault, BootstrapFake(), plan, Settings())

    auth = vault.read_note("memory://sample/modules/samplepkg-auth")
    assert auth["source"] == "distilled"
    assert "Handles samplepkg.auth duties" in auth["body"]
    # deterministic link from the import graph
    assert "memory://sample/modules/samplepkg-store" in auth["links"]["depends_on"]

    fn = vault.read_note("memory://sample/functions/samplepkg-auth-login")
    assert fn["links"]["part_of"] == ["memory://sample/modules/samplepkg-auth"]

    conv = vault.search("ruff line length")
    assert conv and conv[0]["type"] == "convention"

    index_text = (mounts["sample"] / "_index.md").read_text()
    assert "tremula:auto" in index_text
    assert "[[modules/samplepkg-auth]]" in index_text
    assert any(line.startswith("module memory://") for line in log)


def test_bootstrap_idempotent_rerun(repo):
    root, vault, mounts = repo
    plan = plan_bootstrap(root)
    run_bootstrap(vault, BootstrapFake(), plan, Settings())
    files_before = sorted(p.relative_to(mounts["sample"])
                          for p in mounts["sample"].rglob("*.md"))
    run_bootstrap(vault, BootstrapFake(), plan_bootstrap(root), Settings())
    files_after = sorted(p.relative_to(mounts["sample"])
                         for p in mounts["sample"].rglob("*.md"))
    assert files_before == files_after  # updates, never duplicates


def test_bootstrap_never_clobbers_manual_note(repo):
    root, vault, mounts = repo
    manual_body = "# samplepkg.auth\n\nHAND-WRITTEN: precious analysis.\n"
    vault.write_note("samplepkg.auth", manual_body, type="module")  # source=manual
    log = run_bootstrap(vault, BootstrapFake(), plan_bootstrap(root), Settings())
    note = vault.read_note("memory://sample/modules/samplepkg-auth")
    assert "HAND-WRITTEN: precious analysis." in note["body"]
    assert note["source"] == "manual"
    assert any("skip module samplepkg.auth: manual note exists" in line for line in log)


def test_roots_draft_written_only_when_root_declared(repo, tmp_path):
    root, vault, mounts = repo
    # no registry/no roots -> no contracts
    run_bootstrap(vault, BootstrapFake(), plan_bootstrap(root), Settings())
    assert not list(mounts["sample"].glob("contracts/*"))

    # declare a root and mount it
    root_vault = tmp_path / "roots" / "sample-inventory"
    root_vault.mkdir(parents=True)
    registry = Registry.model_validate({
        "projects": {"sample": {"path": str(mounts["sample"]), "repo": str(root)}},
        "roots": {"sample-inventory": {"members": ["sample"], "path": str(root_vault)}},
    })
    mounts2 = dict(mounts, **{"sample-inventory": root_vault})
    vault2 = VaultService(mounts2, vault.index, project="sample")
    run_bootstrap(vault2, BootstrapFake(), plan_bootstrap(root), Settings(),
                  registry=registry)
    contracts = list(root_vault.glob("contracts/*.md"))
    assert len(contracts) == 1
    text = contracts[0].read_text()
    assert "api.example.com/items" in text and "samplepkg.api_client" in text
    assert "type: contract" in text


def test_brief_bootstrap_zero_llm_stubs_with_links(repo):
    root, vault, mounts = repo
    # provider=None: brief mode must need NO LLM at all
    log = run_bootstrap(vault, None, plan_bootstrap(root), Settings(), brief=True)
    auth = vault.read_note("memory://sample/modules/samplepkg-auth")
    assert auth["source"] == "distilled"
    assert "Authentication for the sample app." in auth["body"]  # docstring, free
    assert "`login` (function)" in auth["body"]                   # AST symbols
    # links still graph-derived even in brief mode
    assert "memory://sample/modules/samplepkg-store" in auth["links"]["depends_on"]
    # no LLM passes ran
    assert not list(mounts["sample"].glob("functions/*"))
    assert not any(line.startswith("write ") for line in log)  # no conventions ops
    # ts file without docstring gets the stub marker
    client = vault.read_note("memory://sample/modules/web-client")
    assert "brief bootstrap stub" in client["body"]


def test_brief_stub_is_enriched_by_distiller_later(repo):
    from tremula.distiller import distill

    root, vault, _ = repo
    run_bootstrap(vault, None, plan_bootstrap(root), Settings(), brief=True)

    class EnrichingProvider:
        def complete(self, prompt: str) -> str:
            # the ambient distiller reuses the exact existing title -> in-place update
            return json.dumps({"ops": [{"action": "write", "title": "samplepkg.auth",
                                        "type": "module", "scope": "shared",
                                        "content": "# samplepkg.auth\n\nNow richly "
                                                   "documented after a work session.\n"}]})

    applied = distill([{"event": "Stop", "payload": {"text": "worked on auth"}}],
                      vault, EnrichingProvider())
    assert applied == ["write memory://sample/modules/samplepkg-auth"]
    note = vault.read_note("memory://sample/modules/samplepkg-auth")
    assert "richly documented" in note["body"]      # stub grew into knowledge
    assert "brief bootstrap stub" not in note["body"]


def test_cli_bootstrap_brief(repo, monkeypatch, capsys):
    from tremula.cli import main

    root, _, _ = repo
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    monkeypatch.chdir(root)
    main(["registry", "init", "--name", "sample"])
    capsys.readouterr()
    assert main(["bootstrap", "--brief"]) == 0
    out = capsys.readouterr().out
    assert "[brief]" in out


def test_cli_bootstrap_dry_run(repo, monkeypatch, capsys):
    from tremula.cli import main

    root, _, _ = repo
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    monkeypatch.chdir(root)
    assert main(["registry", "init", "--name", "sample"]) == 0
    capsys.readouterr()
    assert main(["bootstrap", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "bootstrap plan" in out and "samplepkg.auth" in out
    assert "dry-run: no LLM calls" in out


def test_module_summary_failure_skips_not_aborts(repo):
    root, vault, _ = repo

    class FlakyProvider(BootstrapFake):
        def complete(self, prompt: str) -> str:
            if "MODULE: samplepkg.auth" in prompt:
                return "no json at all, sorry"
            return super().complete(prompt)

    log = run_bootstrap(vault, FlakyProvider(), plan_bootstrap(root), Settings())
    assert any("skip module samplepkg.auth" in line for line in log)
    # the rest of the run still happened
    assert vault.read_note("memory://sample/modules/samplepkg-store")
