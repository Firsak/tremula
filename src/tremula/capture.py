"""Hot-path session capture: cheap append-only NDJSON, no LLM.

Hooks call this on every tool use / prompt / stop. It must never block or fail
a session, so it swallows its own errors and always returns. The expensive work
(LLM distillation) happens later in a detached process (see ``distiller``).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .config import hooks_disabled, sessions_dir

# Hard caps applied at capture time. PostToolUse payloads can embed whole file
# contents; without clipping, session NDJSON balloons and the distiller prompt
# with it. Clipped capture loses verbatim detail but keeps the signal.
CAPTURE_MAX_STR = 2000
CAPTURE_MAX_LIST = 100


def session_file(project: str, session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "session"
    return sessions_dir(project) / f"{safe}.ndjson"


def clip_payload(value, max_str: int = CAPTURE_MAX_STR):
    """Recursively truncate long strings / huge lists in a hook payload."""
    if isinstance(value, str) and len(value) > max_str:
        return value[:max_str] + f"…[+{len(value) - max_str} chars]"
    if isinstance(value, dict):
        return {k: clip_payload(v, max_str) for k, v in value.items()}
    if isinstance(value, list):
        clipped = [clip_payload(v, max_str) for v in value[:CAPTURE_MAX_LIST]]
        if len(value) > CAPTURE_MAX_LIST:
            clipped.append(f"…[+{len(value) - CAPTURE_MAX_LIST} items]")
        return clipped
    return value


def append_event(project: str, session_id: str, event: str, payload: dict) -> bool:
    """Append one event line. Returns False if disabled or on any error (never raises)."""
    if hooks_disabled():
        return False
    try:
        path = session_file(project, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {"ts": time.time(), "event": event, "payload": clip_payload(payload)},
            ensure_ascii=False,
        )
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except Exception:
        return False


def read_session(path: str | Path) -> list[dict]:
    """Read an NDJSON session file into a list of events (skips bad lines)."""
    events, _ = read_session_since(path, 0)
    return events


def read_session_since(path: str | Path, offset: int) -> tuple[list[dict], int]:
    """Read events appended after byte ``offset``; return (events, new_offset).

    Powers incremental distillation: each run consumes only what arrived since
    the previous one. Only complete lines are consumed (the hook may be
    mid-append); a truncated/rotated file resets the offset to zero.
    """
    p = Path(path)
    if not p.exists():
        return [], 0
    size = p.stat().st_size
    if size < offset:
        offset = 0  # file shrank (rotated/cleared) — start over
    if size == offset:
        return [], offset
    with p.open("rb") as fh:
        fh.seek(offset)
        data = fh.read()
    end = data.rfind(b"\n")
    if end == -1:
        return [], offset  # no complete new line yet
    events: list[dict] = []
    for raw in data[: end + 1].splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return events, offset + end + 1
