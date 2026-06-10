"""Central paths and the distiller provider abstraction.

All mutable, rebuildable state lives under ``$TREMULA_HOME`` (default
``~/.tremula``): the registry, the per-project SQLite index, and per-session
NDJSON capture logs. The distiller's LLM is chosen here behind a small config so
switching from the default ``claude -p`` subscription path to the Anthropic API
or a local model is one setting, not a code change (see decision
``stdio-transport``).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

DEFAULT_HOME_ENV = "TREMULA_HOME"
HOOKS_DISABLED_ENV = "TREMULA_HOOKS_DISABLED"


def tremula_home() -> Path:
    """The root for all rebuildable state. Honors ``$TREMULA_HOME``."""
    raw = os.environ.get(DEFAULT_HOME_ENV, "~/.tremula")
    return Path(os.path.expandvars(raw)).expanduser().resolve()


def sessions_dir(project: str) -> Path:
    return tremula_home() / "sessions" / project


def index_path(project: str) -> Path:
    return tremula_home() / "index" / f"{project}.sqlite"


def config_path() -> Path:
    return tremula_home() / "config.yaml"


def hooks_disabled() -> bool:
    return os.environ.get(HOOKS_DISABLED_ENV, "").strip().lower() in {"1", "true", "yes"}


class ProviderConfig(BaseModel):
    """How the distiller calls an LLM.

    ``kind="claude-cli"`` shells out to ``claude -p`` (zero setup, uses the
    user's subscription). ``kind="anthropic"`` uses the Anthropic API with
    ``model`` + an API key (from ``auth_env``). ``base_url`` allows an
    OpenAI/Anthropic-compatible local endpoint (Ollama, llama.cpp).
    """

    kind: str = "claude-cli"
    model: str = "claude-haiku-4-5-20251001"
    base_url: str | None = None
    auth_env: str = "ANTHROPIC_API_KEY"


class Settings(BaseModel):
    """Tunables with sane defaults; overridable via ``config.yaml``."""

    provider: ProviderConfig = ProviderConfig()
    hot_notes: int = 5  # how many notes to inject at SessionStart beyond _index
    max_note_chars: int = 6000  # soft per-note size limit (consolidation pressure)
    max_injection_chars: int = 8000  # cap on the SessionStart block


def load_settings() -> Settings:
    """Load settings from ``config.yaml`` if present, else defaults."""
    path = config_path()
    if not path.exists():
        return Settings()
    import yaml

    raw = yaml.safe_load(path.read_text()) or {}
    return Settings.model_validate(raw)
