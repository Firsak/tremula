"""Stage 6 acceptance: roots/federation — root add CLI, per-side contract
sections (surgical merge, drift visible), distiller federation rule + contract
op, mount-set enforcement for roots."""

from __future__ import annotations

import json

import pytest

from tremula.cli import main
from tremula.contracts import upsert_contract_section
from tremula.distiller import apply_ops, build_prompt, distill
from tremula.index import Index
from tremula.memory_uri import MemoryURIError
from tremula.vault import VaultService


@pytest.fixture
def federation(tmp_path, monkeypatch):
    """Two ramets (webapp, api) sharing one root (webapp-api)."""
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    vaults = {}
    for name in ("webapp", "api"):
        v = tmp_path / name / "tremula-vault"
        v.mkdir(parents=True)
        (v / "_index.md").write_text(f"---\ntype: index\nscope: shared\n---\n\n# {name}\n")
        vaults[name] = v
    root = tmp_path / "roots" / "webapp-api"
    root.mkdir(parents=True)

    def side(project: str) -> VaultService:
        mounts = {project: vaults[project], "webapp-api": root}
        index = Index(tmp_path / "home" / "index" / f"{project}.sqlite")
        index.rebuild(mounts)
        return VaultService(mounts, index, project=project)

    return side, root


# ---- per-side contract sections ---------------------------------------------------

def test_both_sides_converge_on_one_note(federation):
    side, root = federation
    webapp, api = side("webapp"), side("api")

    uri_w = upsert_contract_section(webapp, "webapp-api", "POST /items", "webapp",
                                    "consumer", "Sends {name, qty}; expects 201 + id.")
    uri_a = upsert_contract_section(api, "webapp-api", "POST /items", "api",
                                    "provider", "Validates qty > 0; returns 201 {id}.")
    assert uri_w == uri_a == "memory://webapp-api/contracts/post-items"
    files = list(root.glob("contracts/*.md"))
    assert len(files) == 1  # one note, two sides
    body = files[0].read_text()
    assert "## Consumer (webapp)" in body and "Sends {name, qty}" in body
    assert "## Provider (api)" in body and "Validates qty > 0" in body


def test_update_replaces_only_own_section(federation):
    side, root = federation
    webapp, api = side("webapp"), side("api")
    upsert_contract_section(webapp, "webapp-api", "POST /items", "webapp",
                            "consumer", "v1 consumer expectations")
    upsert_contract_section(api, "webapp-api", "POST /items", "api",
                            "provider", "v1 provider behavior")
    # provider updates its side; consumer's text must be byte-identical
    upsert_contract_section(api, "webapp-api", "POST /items", "api",
                            "provider", "v2 provider behavior: qty <= 100 now")
    body = next(root.glob("contracts/*.md")).read_text()
    assert "v2 provider behavior" in body and "v1 provider behavior" not in body
    assert "v1 consumer expectations" in body  # drift now VISIBLE: v1 vs v2 side by side


def test_contract_skeleton_frontmatter_and_search(federation):
    side, _ = federation
    webapp = side("webapp")
    uri = upsert_contract_section(webapp, "webapp-api", "GET /health", "webapp",
                                  "consumer", "Polls every 30s.")
    note = webapp.read_note(uri)
    assert note["type"] == "contract" and note["source"] == "distilled"
    assert any(h["uri"] == uri for h in webapp.search("polls health"))


def test_root_not_in_mount_set_is_rejected(federation):
    side, _ = federation
    webapp = side("webapp")
    with pytest.raises(MemoryURIError, match="not in the mount set"):
        upsert_contract_section(webapp, "other-root", "X", "webapp", "consumer", "x")
    with pytest.raises(ValueError, match="role"):
        upsert_contract_section(webapp, "webapp-api", "X", "webapp", "editor", "x")


# ---- distiller integration ----------------------------------------------------------

def test_federation_rule_in_prompt_only_with_roots():
    with_roots = build_prompt([{"event": "Stop", "payload": {}}], roots=["webapp-api"])
    assert "FEDERATION" in with_roots and "webapp-api" in with_roots
    without = build_prompt([{"event": "Stop", "payload": {}}])
    assert "FEDERATION" not in without


def test_apply_ops_contract_action_and_bad_root_skip(federation):
    side, root = federation
    api = side("api")
    ops = [
        {"action": "contract", "root": "webapp-api", "title": "DELETE /items/{id}",
         "role": "provider", "content": "Soft-deletes; 204."},
        {"action": "contract", "root": "ghost-root", "title": "X",
         "role": "provider", "content": "x"},
    ]
    applied = apply_ops(api, ops)
    assert any(line.startswith("contract memory://webapp-api/") for line in applied)
    assert any("skip contract" in line for line in applied)
    assert "Soft-deletes" in next(root.glob("contracts/delete-items-id.md")).read_text()


def test_distill_emits_contract_via_federation(federation):
    side, root = federation
    webapp = side("webapp")

    class FederatedProvider:
        def __init__(self):
            self.prompts = []

        def complete(self, prompt: str) -> str:
            self.prompts.append(prompt)
            return json.dumps({"ops": [{
                "action": "contract", "root": "webapp-api", "title": "POST /items",
                "role": "consumer", "content": "Now sends an idempotency key header.",
            }]})

    provider = FederatedProvider()
    applied = distill([{"event": "Stop", "payload": {"text": "added idempotency key "
                                                             "to the items call"}}],
                      webapp, provider)
    assert "webapp-api" in provider.prompts[0]  # the rule told it the root exists
    assert applied == ["contract memory://webapp-api/contracts/post-items [consumer]"]
    assert "idempotency key" in next(root.glob("contracts/post-items.md")).read_text()


# ---- root add CLI --------------------------------------------------------------------

@pytest.fixture
def registered_pair(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    for name in ("webapp", "api"):
        repo = tmp_path / name
        (repo / "tremula-vault").mkdir(parents=True)
        monkeypatch.chdir(repo)
        assert main(["registry", "init", "--name", name]) == 0
    return tmp_path


def test_root_add_cli_declares_and_mounts(registered_pair, monkeypatch, capsys):
    tmp_path = registered_pair
    capsys.readouterr()
    assert main(["root", "add", "webapp-api", "--members", "webapp,api"]) == 0
    out = capsys.readouterr().out
    assert "declared root 'webapp-api'" in out

    monkeypatch.chdir(tmp_path / "webapp")
    assert main(["registry"]) == 0
    out = capsys.readouterr().out
    assert "memory://webapp-api/" in out  # root is in webapp's mount set


def test_root_add_cli_validation(registered_pair, capsys):
    capsys.readouterr()
    assert main(["root", "add", "bad", "--members", "webapp,ghost"]) == 1
    assert "unknown project member" in capsys.readouterr().err
    assert main(["root", "add", "solo", "--members", "webapp"]) == 1
    assert "at least two members" in capsys.readouterr().err
    assert main(["root", "add", "ok", "--members", "webapp,api"]) == 0
    capsys.readouterr()
    assert main(["root", "add", "ok", "--members", "webapp,api"]) == 1
    assert "already declared" in capsys.readouterr().err
    assert main(["root", "add", "ok", "--members", "webapp,api", "--force"]) == 0
