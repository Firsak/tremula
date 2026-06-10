"""Live distiller tests — exercise a REAL LLM to prove JSON-adherence.

These are opt-in and skipped by default (they cost tokens and need network /
a logged-in CLI). Enable with::

    TREMULA_LIVE_TESTS=1 uv run pytest -m live -v

- ``claude -p`` path: needs the `claude` binary on PATH.
- Anthropic API path: needs ``ANTHROPIC_API_KEY``.

They assert the model returns parseable ops in our schema and that any applied
ops produce valid notes — i.e. the distiller round-trips against a live model,
not just a FakeProvider.
"""

from __future__ import annotations

import os
import shutil

import pytest

from tremula.config import ProviderConfig
from tremula.distiller import (
    ClaudeCliProvider,
    build_prompt,
    distill,
    parse_ops,
    provider_from_config,
)
from tremula.index import Index
from tremula.note import NoteType
from tremula.vault import VaultService

pytestmark = pytest.mark.live

LIVE = os.environ.get("TREMULA_LIVE_TESTS", "").lower() in {"1", "true", "yes"}

# A session that unambiguously contains one durable decision worth a note.
FIXTURE_EVENTS = [
    {"event": "UserPromptSubmit",
     "payload": {"text": "We decided to use stdio as the MCP transport for now, "
                         "deferring an HTTP daemon until cold starts hurt."}},
    {"event": "PostToolUse",
     "payload": {"tool_name": "Edit", "file": "server.py",
                 "note": "implemented FastMCP stdio server"}},
    {"event": "Stop", "payload": {}},
]


def _live_vault(tmp_path, monkeypatch) -> tuple[VaultService, dict]:
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    vault_dir = tmp_path / "proj" / "tremula-vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "_index.md").write_text("---\ntype: index\nscope: shared\n---\n\n# Proj\n")
    mounts = {"proj": vault_dir}
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    index.rebuild(mounts)
    return VaultService(mounts, index, project="proj"), mounts


@pytest.mark.skipif(not LIVE or not shutil.which("claude"),
                    reason="set TREMULA_LIVE_TESTS=1 and have the `claude` CLI on PATH")
def test_claude_cli_returns_parseable_ops(tmp_path, monkeypatch):
    provider = ClaudeCliProvider()
    raw = provider.complete(build_prompt(FIXTURE_EVENTS))
    ops = parse_ops(raw)
    # JSON-adherence: response parses into our ops schema (list of action dicts).
    assert isinstance(ops, list), f"model did not return parseable ops; raw={raw[:300]!r}"
    for op in ops:
        assert op.get("action") in {"write", "link"}, f"bad op: {op}"


@pytest.mark.skipif(not LIVE or not shutil.which("claude"),
                    reason="set TREMULA_LIVE_TESTS=1 and have the `claude` CLI on PATH")
def test_claude_cli_distill_writes_valid_notes(tmp_path, monkeypatch):
    vault, mounts = _live_vault(tmp_path, monkeypatch)
    applied = distill(FIXTURE_EVENTS, vault, ClaudeCliProvider())
    assert isinstance(applied, list)
    # Every note the model wrote must be a valid, re-readable note.
    written = [line for line in applied if line.startswith("write ")]
    for line in written:
        uri = line.split(" ", 1)[1]
        note = vault.read_note(uri)
        assert NoteType(note["type"]) in NoteType
        assert note["body"].strip()
    # With this fixture we expect the model to capture at least the stdio decision.
    assert written, f"live distill produced no notes; applied={applied}"


@pytest.mark.skipif(not LIVE or not os.environ.get("ANTHROPIC_API_KEY"),
                    reason="set TREMULA_LIVE_TESTS=1 and ANTHROPIC_API_KEY for the API path")
def test_anthropic_provider_returns_parseable_ops(tmp_path, monkeypatch):
    provider = provider_from_config(ProviderConfig(kind="anthropic"))
    ops = parse_ops(provider.complete(build_prompt(FIXTURE_EVENTS)))
    assert isinstance(ops, list)
    for op in ops:
        assert op.get("action") in {"write", "link"}
