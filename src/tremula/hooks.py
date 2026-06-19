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
from .config import (
    HOOKS_DISABLED_ENV,
    hooks_disabled,
    index_path,
    load_settings,
    sessions_dir,
)
from .distiller import should_distill
from .index import Index
from .index_md import sync_index_auto_section
from .injection import (
    build_attachment,
    build_injection,
    load_injected,
    record_injected,
    save_injected,
)
from .registry import resolve_session
from .vault import VaultService
from .workctx import working_context

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
        # Distiller stderr goes to a per-project log instead of the void —
        # the only way to debug a detached background process.
        log_path = sessions_dir(project) / "distill.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log:
            subprocess.Popen(
                [sys.executable, "-m", "tremula", "distill", str(session_path),
                 "--project", project, "--trigger", trigger],
                stdout=subprocess.DEVNULL,
                stderr=log,
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
            # Mechanically surface any note files not yet linked in _index.md
            # (auto-section between markers), BEFORE rebuilding and injecting —
            # the injected index then already lists them.
            if ctx.vault_root is not None:
                sync_index_auto_section(ctx.vault_root, ctx.project)
            index = Index(index_path(ctx.project))
            index.rebuild(ctx.mounts)
            # Working-tree paths gate provisional notes. No session yet at
            # SessionStart, so only git status contributes (NEW working_context call).
            wc = working_context(None, repo_root=cwd)
            block, uris = build_injection(
                ctx.mounts, ctx.project, index, load_settings(),
                working_paths=set(wc["paths"]),
            )
            # RESET (overwrite) the dedupe sidecar: after a compact/resume the
            # previously attached notes may be gone from context, so everything
            # except what we inject right now becomes attachable again.
            save_injected(session_file(ctx.project, session_id), uris)
            if block:
                sys.stdout.write(block + "\n")
        except Exception:
            pass
        return 0

    if event in CAPTURE_EVENTS:
        append_event(ctx.project, session_id, event, payload)

    if event == "UserPromptSubmit":
        # Proactive attach (funnel step 3): notes scoped by the WORKING CONTEXT
        # (recent file ops, git status, cwd) — never by prompt words. Entirely
        # fail-silent; stdout is added to the prompt's context by Claude Code.
        try:
            path = session_file(ctx.project, session_id)
            wc = working_context(path, repo_root=cwd)
            ctx_terms = wc["terms"]
            if ctx_terms:
                settings = load_settings()
                index = Index(index_path(ctx.project))
                index.refresh(ctx.mounts)
                vault = VaultService(ctx.mounts, index, project=ctx.project)
                block, attached = build_attachment(
                    vault, ctx_terms, exclude=load_injected(path), settings=settings,
                    working_paths=set(wc["paths"]),
                )
                if block:
                    sys.stdout.write(block + "\n")
                    record_injected(path, attached)
        except Exception:
            pass

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
