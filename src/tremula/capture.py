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


def session_file(project: str, session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "session"
    return sessions_dir(project) / f"{safe}.ndjson"


def append_event(project: str, session_id: str, event: str, payload: dict) -> bool:
    """Append one event line. Returns False if disabled or on any error (never raises)."""
    if hooks_disabled():
        return False
    try:
        path = session_file(project, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {"ts": time.time(), "event": event, "payload": payload},
            ensure_ascii=False,
        )
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except Exception:
        return False


def read_session(path: str | Path) -> list[dict]:
    """Read an NDJSON session file into a list of events (skips bad lines)."""
    events: list[dict] = []
    p = Path(path)
    if not p.exists():
        return events
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
