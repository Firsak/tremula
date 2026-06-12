"""The agent-agnostic provider layer: generic CLI completer, auto-detection,
preset/explicit-command resolution, and back-compat. No live model is called —
the CLI provider is exercised against `cat`/`printf` so behavior is deterministic.
"""

from __future__ import annotations

import pytest

import tremula.distiller as distiller
from tremula.config import AGENT_PRESETS, ProviderConfig
from tremula.distiller import (
    ClaudeCliProvider,
    CliProvider,
    detect_agents,
    provider_from_config,
)

# ---- CliProvider: the universal mechanism ---------------------------------------

def test_prompt_piped_on_stdin_when_no_token():
    # `cat` echoes stdin -> the prompt is piped, not passed as an arg.
    assert CliProvider(["cat"]).complete("hello stdin").strip() == "hello stdin"


def test_prompt_substituted_as_arg_when_token_present():
    # `{prompt}` -> the prompt becomes an argv element; stdin is left empty.
    assert CliProvider(["printf", "%s", "{prompt}"]).complete("hello arg") == "hello arg"


def test_model_token_substituted():
    assert CliProvider(["printf", "%s", "{model}"], model="m-1").complete("x") == "m-1"


def test_empty_command_rejected():
    with pytest.raises(ValueError, match="non-empty command"):
        CliProvider([])


def test_missing_binary_gives_actionable_error():
    with pytest.raises(RuntimeError, match="not on PATH"):
        CliProvider(["tremula-no-such-binary-xyz"]).complete("x")


# ---- provider_from_config: resolution -------------------------------------------

def test_cli_with_explicit_command():
    p = provider_from_config(ProviderConfig(kind="cli", command=["cat"]))
    assert isinstance(p, CliProvider)
    assert p.complete("x").strip() == "x"


def test_cli_with_named_agent_preset():
    p = provider_from_config(ProviderConfig(kind="cli", agent="gemini"))
    assert p.command == AGENT_PRESETS["gemini"]


def test_cli_needs_command_or_agent():
    with pytest.raises(RuntimeError, match="needs `command`"):
        provider_from_config(ProviderConfig(kind="cli"))


def test_unknown_agent_preset_rejected():
    with pytest.raises(RuntimeError, match="unknown agent preset"):
        provider_from_config(ProviderConfig(kind="cli", agent="nope"))


def test_auto_uses_pinned_agent():
    p = provider_from_config(ProviderConfig(kind="auto", agent="codex"))
    assert p.command == AGENT_PRESETS["codex"]


def test_auto_picks_single_detected_cli(monkeypatch):
    monkeypatch.setattr(distiller.shutil, "which",
                        lambda n: f"/usr/bin/{n}" if n == "gemini" else None)
    assert detect_agents() == ["gemini"]
    p = provider_from_config(ProviderConfig(kind="auto"))
    assert p.command == AGENT_PRESETS["gemini"]


def test_auto_refuses_to_guess_when_multiple_detected(monkeypatch):
    monkeypatch.setattr(distiller.shutil, "which", lambda n: f"/usr/bin/{n}")
    with pytest.raises(RuntimeError, match="multiple agent CLIs"):
        provider_from_config(ProviderConfig(kind="auto"))


def test_auto_none_and_no_key_raises(monkeypatch):
    monkeypatch.setattr(distiller.shutil, "which", lambda n: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="no agent CLI found"):
        provider_from_config(ProviderConfig(kind="auto"))


def test_auto_none_with_key_falls_back_to_anthropic(monkeypatch):
    monkeypatch.setattr(distiller.shutil, "which", lambda n: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    # Don't require the optional `anthropic` SDK: stub the constructor.
    monkeypatch.setattr(distiller, "AnthropicProvider",
                        lambda **kw: ("anthropic", kw))
    result = provider_from_config(ProviderConfig(kind="auto"))
    assert result[0] == "anthropic"


def test_claude_cli_kind_is_back_compat(monkeypatch):
    p = provider_from_config(ProviderConfig(kind="claude-cli"))
    assert isinstance(p, ClaudeCliProvider) and isinstance(p, CliProvider)
    assert p.command[:2] == ["claude", "-p"]


# ---- describe(): no vendor lock-in ----------------------------------------------

def test_default_describe_advertises_no_lock_in_no_key():
    desc = ProviderConfig().describe()  # default kind="auto"
    low = desc.lower()
    assert "auto-detect" in low
    assert "no provider lock-in" in low
    assert "no api key" in low
    # Not claude-centric: it presents claude/gemini/codex as equal options.
    assert "gemini" in desc and "codex" in desc


def test_anthropic_describe_names_the_key():
    assert "ANTHROPIC_API_KEY" in ProviderConfig(kind="anthropic").describe()


def test_cli_describe_names_the_agent():
    assert "gemini" in ProviderConfig(kind="cli", agent="gemini").describe()
