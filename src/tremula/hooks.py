"""Ambient layer dispatch: ``tremula hook <event>`` reads a Claude Code hook
payload on stdin and routes it.

- Capture events (PostToolUse, UserPromptSubmit, Stop) append to the session
  NDJSON — cheap, no LLM.
- SessionStart prints the injection block to stdout (Claude Code adds it to
  context).
- Stop / PreCompact / SessionEnd additionally spawn a DETACHED distiller so the
  hook returns instantly.

Every path returns 0. A hook must never slow or fail a session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .capture import append_event, session_file
from .config import HOOKS_DISABLED_ENV, hooks_disabled, index_path, load_settings
from .distiller import should_distill
from .index import Index
from .injection import build_injection
from .registry import resolve_session

CAPTURE_EVENTS = {"PostToolUse", "PreToolUse", "UserPromptSubmit", "Stop", "Notification"}
DISTILL_EVENTS = {"Stop", "PreCompact", "SessionEnd"}


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def _spawn_distiller(session_path: Path, project: str, trigger: str = "Stop") -> None:
    """Launch the distiller fully detached; ignore all failures.

    CRITICAL: the distiller runs ``claude -p`` inside the project, and that
    headless session would itself fire these hooks — an exponential fork bomb.
    We pass ``TREMULA_HOOKS_DISABLED=1`` (and a re-entrancy marker) so every hook
    fired by the distiller's own LLM call returns immediately without spawning.
    """
    env = {
        **os.environ,
        HOOKS_DISABLED_ENV: "1",
        "TREMULA_DISTILLING": "1",
    }
    try:
        subprocess.Popen(
            [sys.executable, "-m", "tremula", "distill", str(session_path),
             "--project", project, "--trigger", trigger],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # detach from the hook's process group
            env=env,
        )
    except Exception:
        pass


def run_hook(event: str, payload: dict | None = None) -> int:
    """Handle one hook event. Always returns 0."""
    # Hard stop for re-entrancy: a distiller's own claude -p must not re-trigger
    # capture/injection/distillation. This is the fork-bomb breaker. The flag is
    # set (to "1") on the distiller's environment; hooks_disabled() also accepts
    # "true"/"yes".
    if hooks_disabled():
        return 0
    payload = payload if payload is not None else _read_payload()
    cwd = payload.get("cwd") or os.getcwd()
    session_id = str(payload.get("session_id") or "session")

    try:
        ctx = resolve_session(cwd=cwd)
    except Exception:
        return 0  # never let registry problems break a session
    if not ctx.project:
        return 0  # unregistered project: nothing to capture or inject

    if event == "SessionStart":
        try:
            index = Index(index_path(ctx.project))
            index.rebuild(ctx.mounts)
            block = build_injection(ctx.mounts, ctx.project, index, load_settings())
            if block:
                sys.stdout.write(block + "\n")
        except Exception:
            pass
        return 0

    if event in CAPTURE_EVENTS:
        append_event(ctx.project, session_id, event, payload)

    if event in DISTILL_EVENTS:
        # Stop fires on every assistant turn: only spawn a process when there
        # are new events, no distill is in flight, and the interval has passed
        # (PreCompact/SessionEnd flush regardless). Fail closed — a broken
        # check must not cost a claude -p call.
        path = session_file(ctx.project, session_id)
        try:
            ok, _reason = should_distill(
                path, trigger=event,
                min_interval=load_settings().distill_min_interval_s,
            )
        except Exception:
            ok = False
        if ok:
            _spawn_distiller(path, ctx.project, trigger=event)

    return 0
