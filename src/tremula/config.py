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


# Best-effort presets for known agent CLIs: name -> argv that runs it as a
# one-shot completer. A "{prompt}" token is replaced by the prompt text (passed
# as that arg); without it, the prompt is piped on stdin. "{model}" is replaced
# by ``model``. These are not exhaustive and flags vary by CLI version — any
# stdin/arg CLI works via ``kind="cli"`` + an explicit ``command``.
AGENT_PRESETS: dict[str, list[str]] = {
    "claude": ["claude", "-p", "--output-format", "text"],  # prompt on stdin
    "gemini": ["gemini", "-p", "{prompt}"],                 # prompt as arg
    "codex": ["codex", "exec", "{prompt}"],                 # prompt as arg
}


class ProviderConfig(BaseModel):
    """How the distiller calls an LLM — agent-agnostic, no provider lock-in.

    - ``kind="auto"`` (default): detect a CLI agent on PATH (any key in
      :data:`AGENT_PRESETS`: claude / gemini / codex / …) and use it — no API
      key. If several are installed, set ``agent`` to pick one. If none are and
      ``$auth_env`` holds a key, fall back to the Anthropic API.
    - ``kind="cli"``: run an explicit ``command`` (or a named ``agent`` preset);
      the prompt fills a ``{prompt}`` arg if present, else is piped on stdin.
    - ``kind="anthropic"``: Anthropic API (``model`` + key from ``auth_env``;
      ``base_url`` allows an Anthropic-compatible local endpoint).
    - ``kind="claude-cli"``: back-compat alias for the claude preset.
    """

    kind: str = "auto"
    model: str = "claude-haiku-4-5-20251001"  # used by anthropic + any {model} token
    base_url: str | None = None
    auth_env: str = "ANTHROPIC_API_KEY"
    command: list[str] | None = None  # kind="cli": explicit argv to run
    agent: str | None = None  # pin a preset (a key in AGENT_PRESETS) for auto/cli

    def describe(self) -> str:
        """One line: which backend will run + exactly what auth it needs.

        Surfaced in bootstrap output so a caller never has to guess whether
        ``$auth_env`` is required — the CLI paths need no API key.
        """
        if self.kind == "auto":
            pin = f" (pinned: {self.agent})" if self.agent else ""
            return ("auto-detect a CLI agent on PATH — claude / gemini / codex / "
                    f"…{pin}; falls back to the Anthropic API only if a key is set. "
                    "No provider lock-in; no API key for the CLI path")
        if self.kind in ("cli", "claude-cli"):
            target = self.agent or (self.command[0] if self.command
                                    else "claude" if self.kind == "claude-cli"
                                    else "configured CLI")
            return f"CLI agent `{target}` — runs locally, no API key needed"
        if self.kind == "anthropic":
            return f"Anthropic API, model {self.model} — needs ${self.auth_env}"
        return f"{self.kind}, model {self.model}"


class Settings(BaseModel):
    """Tunables with sane defaults; overridable via ``config.yaml``."""

    provider: ProviderConfig = ProviderConfig()
    hot_notes: int = 5  # how many notes to inject at SessionStart beyond _index
    max_note_chars: int = 6000  # soft per-note size limit (consolidation pressure)
    max_injection_chars: int = 8000  # cap on the SessionStart block
    # Claude Code fires Stop after EVERY assistant turn, not once per session —
    # without a minimum interval the distiller (one claude -p call) would run
    # per turn. PreCompact/SessionEnd bypass the interval (final flush).
    distill_min_interval_s: int = 600
    distill_prompt_budget: int = 24000  # max chars of session events per distill prompt
    # By default the distiller may freely rewrite its own (source=distilled)
    # notes. Set true to route those updates through the enrichment judge +
    # no-loss backstop too — safer, costs one extra LLM call per update.
    judge_distilled_updates: bool = False
    # Proactive attach (UserPromptSubmit): scoped by working context
    # (recent file ops, git status, cwd) — never by prompt words (plan §5.3).
    attach_notes: int = 3  # max notes attached per prompt
    attach_max_chars: int = 1500  # hard cap on the whole attachment block
    attach_note_chars: int = 400  # per-note body excerpt length
    workctx_max_paths: int = 10  # how many recent file paths feed the search
    # Bootstrap caps.
    bootstrap_max_modules: int = 40  # one LLM call per module
    bootstrap_functions: int = 10  # key functions (one batched LLM call)
    bootstrap_module_src_chars: int = 6000  # source excerpt per module prompt
    # Bootstrap scan pruning: a machine-wide default of extra directory names to
    # skip, added to the always-junk SKIP_DIRS. Per-project build dirs belong in
    # a repo-root .tremulaignore instead (committed, travels with clones).
    bootstrap_skip_dirs: list[str] = []
    # Self-organization (revision pass).
    revision_every_n_runs: int = 5  # run a revision pass every Nth distill run
    stale_after_days: int = 14  # cold+unlinked distilled notes older than this -> archive
    revision_max_merges: int = 5  # duplicate pairs judged per revision pass (LLM cost bound)


def load_settings() -> Settings:
    """Load settings from ``config.yaml`` if present, else defaults."""
    path = config_path()
    if not path.exists():
        return Settings()
    import yaml

    raw = yaml.safe_load(path.read_text()) or {}
    return Settings.model_validate(raw)
