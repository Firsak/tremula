"""Hardening tests for the Stage 3 distiller fork-bomb + clobber fixes.

After the live ambient loop misbehaved, three fixes landed:
1. recursion guard — a hook returns immediately when hooks are disabled;
2. judged enrichment — the distiller may update a manual note only if an LLM
   judge approves AND a deterministic no-loss backstop confirms nothing is lost;
3. read-before-write — the distiller is shown existing notes in its prompt.
"""

from __future__ import annotations

import json

import pytest

from tremula import hooks
from tremula.distiller import build_prompt, content_preserved, distill
from tremula.index import Index
from tremula.registry import SessionContext
from tremula.vault import VaultService


@pytest.fixture
def vault_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_HOOKS_DISABLED", raising=False)
    vault_dir = tmp_path / "proj" / "tremula-vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "_index.md").write_text("---\ntype: index\nscope: shared\n---\n\n# Proj\n")
    mounts = {"proj": vault_dir}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    return VaultService(mounts, index, project="proj"), mounts


class ScriptedProvider:
    """Returns the judge response when handed a judge prompt, else the ops response."""

    def __init__(self, ops_response: str, judge_response: str | None = None):
        self.ops_response = ops_response
        self.judge_response = judge_response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "ENRICHMENT JUDGE" in prompt:
            return self.judge_response or '{"decision": "reject", "reason": "none"}'
        return self.ops_response


def _write_op(title: str, content: str, type_: str = "decision") -> str:
    return json.dumps({"ops": [{"action": "write", "title": title,
                               "type": type_, "content": content}]})


def _judge(decision: str, merged: str | None = None, reason: str = "") -> str:
    verdict: dict = {"decision": decision, "reason": reason}
    if merged is not None:
        verdict["merged"] = merged
    return json.dumps(verdict)


# ---- Fix 1: recursion guard ------------------------------------------------

def test_hook_disabled_returns_immediately(monkeypatch, vault_setup):
    _, mounts = vault_setup
    monkeypatch.setenv("TREMULA_HOOKS_DISABLED", "1")
    spawned = []
    monkeypatch.setattr(hooks, "_spawn_distiller", lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(hooks, "resolve_session",
                        lambda **k: SessionContext(project="proj", mounts=mounts,
                                                   registry_path=mounts["proj"]))
    rc = hooks.run_hook("Stop", {"session_id": "s", "cwd": str(mounts["proj"].parent)})
    assert rc == 0
    assert spawned == []  # the fork-bomb path never fires when disabled


def test_stop_hook_spawns_once_when_enabled(monkeypatch, vault_setup):
    _, mounts = vault_setup
    spawned = []
    monkeypatch.setattr(hooks, "_spawn_distiller", lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(hooks, "resolve_session",
                        lambda **k: SessionContext(project="proj", mounts=mounts,
                                                   registry_path=mounts["proj"]))
    rc = hooks.run_hook("Stop", {"session_id": "s", "cwd": str(mounts["proj"].parent)})
    assert rc == 0
    assert len(spawned) == 1  # exactly one distiller per Stop, no recursion


# ---- Fix 2: judged enrichment of manual notes ------------------------------

ORIGINAL = "# Pinned decision\n\nWe use stdio transport because it is simple and client agnostic."


def _seed_manual(vault) -> str:
    return vault.write_note("Pinned decision", ORIGINAL, type="decision")  # source=manual


def test_enrich_applied_when_judge_approves_and_no_loss(vault_setup):
    vault, _ = vault_setup
    uri = _seed_manual(vault)
    merged = ORIGINAL + "\n\nWe also abstract the distiller provider behind config."
    provider = ScriptedProvider(
        ops_response=_write_op("Pinned decision", "abstract the distiller provider behind config"),
        judge_response=_judge("enrich", merged=merged, reason="adds provider note"),
    )
    applied = distill([{"event": "Stop", "payload": {"text": "provider config"}}], vault, provider)
    assert any(line.startswith(f"enrich {uri}") for line in applied)
    body = vault.read_note(uri)["body"]
    assert "client agnostic" in body          # original preserved
    assert "abstract the distiller provider" in body  # enrichment added


def test_skip_when_judge_rejects(vault_setup):
    vault, _ = vault_setup
    uri = _seed_manual(vault)
    provider = ScriptedProvider(
        ops_response=_write_op("Pinned decision", "thin redundant rewrite"),
        judge_response=_judge("reject", reason="redundant"),
    )
    applied = distill([{"event": "Stop", "payload": {}}], vault, provider)
    assert any("skip enrich" in line and "redundant" in line for line in applied)
    assert vault.read_note(uri)["body"] == ORIGINAL  # untouched


def test_backstop_blocks_lossy_merge_even_if_judge_approves(vault_setup):
    vault, _ = vault_setup
    uri = _seed_manual(vault)
    provider = ScriptedProvider(
        ops_response=_write_op("Pinned decision", "stdio"),
        # judge wrongly approves a merged body that drops almost all original words
        judge_response=_judge("enrich", merged="# Pinned decision\n\nstdio.",
                              reason="looks fine"),
    )
    applied = distill([{"event": "Stop", "payload": {}}], vault, provider)
    assert any("backstop blocked content loss" in line for line in applied)
    assert vault.read_note(uri)["body"] == ORIGINAL  # backstop saved it


def test_distiller_updates_its_own_distilled_note_without_judge(vault_setup):
    vault, _ = vault_setup
    uri = vault.write_note("Auto note", "# Auto note\n\nv1", type="module", source="distilled")
    provider = ScriptedProvider(ops_response=_write_op("Auto note", "# Auto note\n\nv2", "module"))
    applied = distill([{"event": "Stop", "payload": {}}], vault, provider)
    assert applied == [f"write {uri}"]
    assert "v2" in vault.read_note(uri)["body"]
    assert not any("ENRICHMENT JUDGE" in p for p in provider.prompts)  # no judge needed


def test_judge_distilled_opt_in_rejects_bad_update(vault_setup):
    """With judge_distilled_updates on, even the distiller's own notes are guarded."""
    vault, _ = vault_setup
    uri = vault.write_note("Auto note", "# Auto note\n\nrich original distilled content here",
                           type="module", source="distilled")
    provider = ScriptedProvider(
        ops_response=_write_op("Auto note", "thin", "module"),
        judge_response=_judge("reject", reason="would lose content"),
    )
    applied = distill([{"event": "Stop", "payload": {}}], vault, provider,
                      judge_distilled=True)
    assert any("skip enrich" in line for line in applied)
    assert "rich original" in vault.read_note(uri)["body"]  # untouched


def test_judge_distilled_opt_in_applies_good_update_keeping_provenance(vault_setup):
    vault, _ = vault_setup
    original = "# Auto note\n\noriginal distilled fact about the indexer"
    uri = vault.write_note("Auto note", original, type="module", source="distilled")
    merged = original + "\n\nnew fact: rebuild is single-transaction"
    provider = ScriptedProvider(
        ops_response=_write_op("Auto note", "rebuild is single-transaction", "module"),
        judge_response=_judge("enrich", merged=merged, reason="adds fact"),
    )
    applied = distill([{"event": "Stop", "payload": {}}], vault, provider,
                      judge_distilled=True)
    assert any(line.startswith(f"enrich {uri}") for line in applied)
    note = vault.read_note(uri)
    assert "original distilled fact" in note["body"]
    assert "single-transaction" in note["body"]
    assert note["source"] == "distilled"  # provenance preserved, not flipped to manual


def test_judge_distilled_default_off_setting():
    from tremula.config import Settings
    assert Settings().judge_distilled_updates is False


def test_write_note_protect_flag_direct(vault_setup):
    vault, _ = vault_setup
    uri = vault.write_note("Manual", "# Manual\n\nkeep me", type="convention")
    with pytest.raises(PermissionError, match="refusing to overwrite manual"):
        vault.write_note("Manual", "overwrite", type="convention", source="distilled", protect=True)
    assert "keep me" in vault.read_note(uri)["body"]


# ---- no-loss backstop unit --------------------------------------------------

def test_content_preserved_unit():
    original = "We use stdio transport because it is simple and client agnostic"
    assert content_preserved(original, original + " and fast")     # additive -> ok
    assert not content_preserved(original, "stdio")                # thin -> blocked


# ---- Fix 3: read-before-write ----------------------------------------------

def test_distiller_is_shown_existing_notes(vault_setup):
    vault, _ = vault_setup
    vault.write_note("Existing decision", "# Existing decision\n\nbody", type="decision")
    provider = ScriptedProvider(ops_response='{"ops": []}')
    distill([{"event": "Stop", "payload": {"text": "x"}}], vault, provider)
    assert "EXISTING NOTES" in provider.prompts[0]
    assert "Existing decision" in provider.prompts[0]


def test_build_prompt_includes_existing_block():
    prompt = build_prompt([{"event": "Stop", "payload": {}}],
                          existing_notes=[{"uri": "memory://p/a", "title": "A",
                                           "type": "module", "source": "manual", "body": "x"}])
    assert "EXISTING NOTES" in prompt and "memory://p/a" in prompt
