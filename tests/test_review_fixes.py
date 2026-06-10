"""Regression tests for the full-codebase review pass after Stage 3.

Covers: memory:// path-traversal hardening, FTS5 crash-proofing, split_note
content/metadata preservation, enrichment link preservation, Unicode no-loss
backstop, capture clipping, incremental offsets, the distill debounce/lock, the
prompt budget, frontmatter-free injection, and TREMULA_HOME registry anchoring.
"""

from __future__ import annotations

import json
import os

import pytest

from tremula.capture import (
    append_event,
    clip_payload,
    read_session_since,
    session_file,
)
from tremula.config import Settings
from tremula.distiller import (
    acquire_lock,
    build_prompt,
    content_preserved,
    distill,
    load_distill_state,
    release_lock,
    run_distill,
    save_distill_state,
    should_distill,
)
from tremula.index import Index, _fts_query
from tremula.injection import build_injection
from tremula.memory_uri import MemoryURI, MemoryURIError, resolve
from tremula.registry import default_registry_path
from tremula.vault import VaultService


@pytest.fixture
def vault_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TREMULA_HOOKS_DISABLED", raising=False)
    vault_dir = tmp_path / "proj" / "tremula-vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "_index.md").write_text(
        "---\ntype: index\nscope: shared\n---\n\n# Proj Index\n\nentry point\n"
    )
    mounts = {"proj": vault_dir}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    return VaultService(mounts, index, project="proj"), index, mounts


class ScriptedProvider:
    def __init__(self, ops_response: str, judge_response: str | None = None):
        self.ops_response = ops_response
        self.judge_response = judge_response or '{"decision": "reject", "reason": "n"}'
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "ENRICHMENT JUDGE" in prompt:
            return self.judge_response
        return self.ops_response


# ---- security: path traversal ------------------------------------------------

@pytest.mark.parametrize(
    "bad",
    [
        "memory://proj/../secrets",
        "memory://proj/../../etc/passwd",
        "memory://proj/decisions/../../escape",
        "memory://proj/./decisions/x",
        "memory://proj/.hidden/note",
    ],
)
def test_traversal_uris_rejected_at_parse(bad):
    with pytest.raises(MemoryURIError):
        MemoryURI.parse(bad)


def test_resolve_containment_backstop(tmp_path):
    # Even a URI constructed directly (bypassing parse) cannot escape the root.
    uri = MemoryURI(project="proj", path="../escape")
    with pytest.raises(MemoryURIError, match="escapes"):
        resolve(uri, {"proj": tmp_path / "vault"})


def test_read_note_traversal_blocked(vault_setup, tmp_path):
    vault, _, _ = vault_setup
    (tmp_path / "secret.md").write_text("---\ntype: decision\n---\n\n# Secret\n")
    with pytest.raises(MemoryURIError):
        vault.read_note("memory://proj/../secret")


# ---- security/robustness: FTS5 query handling ---------------------------------

@pytest.mark.parametrize(
    "weird",
    ['don\'t "break', "C++ AND NOT (", 'a"b', "((((", "*", "  ", "—…"],
)
def test_search_never_crashes_on_weird_queries(vault_setup, weird):
    vault, _, _ = vault_setup
    vault.write_note("Sane note", "plain searchable text", type="module")
    assert isinstance(vault.search(weird), list)  # may be empty, must not raise


def test_fts_query_tokenizes():
    assert _fts_query('don\'t "break" C++') == "don t break C"
    assert _fts_query("«спросить» по-русски") == "спросить по русски"


def test_search_still_finds_after_sanitize(vault_setup):
    vault, _, _ = vault_setup
    vault.write_note("Auth flow", "JWT-based login, don't cache tokens", type="module")
    hits = vault.search("don't JWT")
    assert hits and hits[0]["uri"].endswith("auth-flow")


# ---- split_note preserves content + metadata ----------------------------------

def test_split_preserves_preamble_links_and_source(vault_setup):
    vault, _, _ = vault_setup
    anchor = vault.write_note("Anchor", "linked from big doc", type="decision")
    big = vault.write_note(
        "Big doc",
        "# Big doc\n\nimportant intro paragraph\n\n## One\n\nalpha\n\n## Two\n\nbeta\n",
        type="architecture",
        links={"depends_on": [anchor]},
        source="distilled",
    )
    children = vault.split_note(big)
    assert len(children) == 2
    parent = vault.read_note(big)
    assert "important intro paragraph" in parent["body"]      # preamble kept
    assert parent["links"]["depends_on"] == [anchor]          # links kept
    assert parent["source"] == "distilled"                    # provenance kept
    for child in children:
        assert vault.read_note(child)["source"] == "distilled"  # inherited


# ---- enrichment preserves original metadata ------------------------------------

ORIGINAL = "# Pinned\n\nWe use stdio transport because it is simple and client agnostic."


def test_enrich_unions_links_and_keeps_scope(vault_setup):
    vault, _, _ = vault_setup
    dep = vault.write_note("Dep", "a dependency", type="architecture")
    uri = vault.write_note("Pinned", ORIGINAL, type="decision", scope="backend",
                           links={"depends_on": [dep]})
    merged = ORIGINAL + "\n\nAlso: provider is config-abstracted."
    provider = ScriptedProvider(
        ops_response=json.dumps({"ops": [{
            "action": "write", "title": "Pinned", "type": "decision",
            "content": "provider is config-abstracted",
            "links": {"implements": ["memory://proj/architecture/dep"]},
        }]}),
        judge_response=json.dumps(
            {"decision": "enrich", "merged": merged, "reason": "adds fact"}),
    )
    applied = distill([{"event": "Stop", "payload": {}}], vault, provider)
    assert any(line.startswith(f"enrich {uri}") for line in applied)
    note = vault.read_note(uri)
    assert note["links"]["depends_on"] == [dep]                      # original kept
    assert "memory://proj/architecture/dep" in note["links"]["implements"]  # new unioned
    assert note["scope"] == "backend"                                # scope kept


# ---- unicode backstop -----------------------------------------------------------

def test_content_preserved_works_for_cyrillic():
    original = "Мы используем стандартный транспорт потому что это просто и надёжно"
    assert content_preserved(original, original + " и быстро")
    assert not content_preserved(original, "стандартный транспорт")  # thin rewrite blocked


# ---- capture clipping -----------------------------------------------------------

def test_capture_clips_huge_payloads(vault_setup):
    huge = {"tool_response": "x" * 100_000, "nested": {"data": ["y" * 50_000] * 200}}
    append_event("proj", "clip", "PostToolUse", huge)
    path = session_file("proj", "clip")
    assert path.stat().st_size < 300_000  # not ~10MB
    line = json.loads(path.read_text().splitlines()[0])
    assert "…[+" in line["payload"]["tool_response"]


def test_clip_payload_caps_lists():
    clipped = clip_payload({"items": list(range(500))})
    assert len(clipped["items"]) == 101  # 100 + truncation marker
    assert "…[+400 items]" in clipped["items"][-1]


# ---- incremental offsets ----------------------------------------------------------

def test_read_session_since_consumes_incrementally(vault_setup):
    append_event("proj", "inc", "UserPromptSubmit", {"text": "first"})
    path = session_file("proj", "inc")
    events, offset = read_session_since(path, 0)
    assert [e["payload"]["text"] for e in events] == ["first"]
    events2, offset2 = read_session_since(path, offset)
    assert events2 == [] and offset2 == offset  # nothing new
    append_event("proj", "inc", "UserPromptSubmit", {"text": "second"})
    events3, offset3 = read_session_since(path, offset)
    assert [e["payload"]["text"] for e in events3] == ["second"]
    assert offset3 > offset


def test_read_session_since_resets_on_truncation(vault_setup):
    append_event("proj", "trunc", "Stop", {})
    path = session_file("proj", "trunc")
    _, offset = read_session_since(path, 0)
    path.write_text("")  # rotated/cleared
    events, new_offset = read_session_since(path, offset)
    assert events == [] and new_offset == 0


# ---- debounce + lock ---------------------------------------------------------------

def _session_with_events(tmp_path) -> str:
    p = tmp_path / "s.ndjson"
    p.write_text(json.dumps({"ts": 1.0, "event": "Stop", "payload": {}}) + "\n")
    return str(p)


def test_should_distill_no_new_events(tmp_path):
    s = _session_with_events(tmp_path)
    size = os.path.getsize(s)
    save_distill_state(s, offset=size, last_run=0.0)
    ok, reason = should_distill(s, trigger="Stop")
    assert not ok and "no new events" in reason


def test_should_distill_debounces_stop_but_flushes_sessionend(tmp_path):
    s = _session_with_events(tmp_path)
    save_distill_state(s, offset=0, last_run=1000.0)
    ok, reason = should_distill(s, trigger="Stop", min_interval=600, now=1100.0)
    assert not ok and "debounced" in reason
    ok, _ = should_distill(s, trigger="SessionEnd", min_interval=600, now=1100.0)
    assert ok  # flush triggers bypass the interval
    ok, _ = should_distill(s, trigger="Stop", min_interval=600, now=1700.0)
    assert ok  # interval elapsed


def test_should_distill_respects_live_lock(tmp_path):
    s = _session_with_events(tmp_path)
    assert acquire_lock(s)  # our own (live) pid holds it
    try:
        ok, reason = should_distill(s, trigger="SessionEnd")
        assert not ok and "in flight" in reason
    finally:
        release_lock(s)


def test_stale_lock_is_broken(tmp_path):
    s = _session_with_events(tmp_path)
    from tremula.distiller import _lock_path
    _lock_path(s).write_text("999999999")  # dead pid
    assert acquire_lock(s)  # stale lock replaced
    release_lock(s)


def test_run_distill_is_incremental_and_locked(vault_setup, tmp_path):
    vault, _, _ = vault_setup
    s = tmp_path / "sess.ndjson"
    s.write_text(json.dumps({"ts": 1.0, "event": "UserPromptSubmit",
                             "payload": {"text": "decide stdio"}}) + "\n")
    provider = ScriptedProvider(json.dumps({"ops": [{
        "action": "write", "title": "Run note", "type": "decision", "content": "x"}]}))
    first = run_distill(str(s), vault, provider, trigger="SessionEnd")
    assert any(line.startswith("write ") for line in first)
    second = run_distill(str(s), vault, provider, trigger="SessionEnd")
    assert second == []  # offset advanced: nothing new to distill
    assert load_distill_state(str(s))["offset"] == s.stat().st_size
    # a held lock makes a concurrent run bail out
    assert acquire_lock(str(s))
    try:
        s.write_text(s.read_text() + json.dumps({"ts": 2.0, "event": "Stop",
                                                 "payload": {}}) + "\n")
        assert run_distill(str(s), vault, provider) == ["skip: distill already in flight"]
    finally:
        release_lock(str(s))


# ---- prompt budget -------------------------------------------------------------------

def test_build_prompt_drops_old_events_within_budget():
    events = [{"event": "PostToolUse", "payload": {"n": i, "blob": "z" * 500}}
              for i in range(100)]
    prompt = build_prompt(events, budget=5000)
    assert "earlier events omitted" in prompt
    assert '"n": 99' in prompt      # newest kept
    assert '"n": 0' not in prompt   # oldest dropped


# ---- injection strips frontmatter -----------------------------------------------------

def test_injection_has_no_yaml_frontmatter(vault_setup):
    vault, index, mounts = vault_setup
    block = build_injection(mounts, "proj", index, Settings())
    assert "# Proj Index" in block
    assert "---" not in block.split("\n\n")[0]
    assert "type: index" not in block


# ---- registry anchored to TREMULA_HOME --------------------------------------------------

def test_default_registry_path_honors_tremula_home(tmp_path, monkeypatch):
    monkeypatch.delenv("TREMULA_REGISTRY", raising=False)
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "isolated"))
    assert default_registry_path() == (tmp_path / "isolated" / "registry.yaml").resolve()
