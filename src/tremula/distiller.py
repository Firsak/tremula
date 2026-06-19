"""The distiller: turn a captured session into durable notes via an LLM.

Runs in a detached process (off the hot path). The LLM provider is abstracted
(``claude -p`` by default; Anthropic API or a local OpenAI-compatible endpoint
by config) so swapping it is one setting. The provider is injectable, so tests
drive distillation with a deterministic fake instead of a live model.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Protocol

from .config import AGENT_PRESETS, HOOKS_DISABLED_ENV, ProviderConfig, load_settings
from .memory_uri import MemoryURIError
from .vault import VaultService

HYGIENE = """\
You maintain a long-lived knowledge vault about a codebase. From the session
events below, extract only DURABLE knowledge and emit note operations.

KEEP: architectural decisions and why; conventions (style, naming, patterns);
module/function purpose and public API; cross-service contracts.
DROP: PR numbers, commit SHAs, transient TODOs, anything that rots within a week,
chit-chat, and one-off debugging steps.

Prefer updating the smallest number of notes. One note = one atomic fact.

You are shown the EXISTING NOTES below. To revise one, reuse its EXACT title so
it updates in place instead of creating a thinner duplicate. Notes marked
`source: manual` are human-authored: you MAY propose an ENRICHED version (reuse
the exact title) that keeps all original content and adds new durable facts — it
passes through a judge that rejects any change which would lose information.
Never propose a thinner rewrite. Only emit a write for genuinely durable knowledge.

For each `write` op, also declare what code the note is ABOUT, so the system can
tell when that code is present in the working tree:
- `subject_paths`: the source files this note describes, relative to the repo root
  (for a decision/convention this may be a config file; omit or leave empty if the
  note is not about specific files).
- `subject_symbols`: the dotted symbol names it describes (e.g. `module.ClassName`,
  `module.function_name`); empty for non-code notes.
Do NOT invent paths — only list files actually touched in the session.

Respond with ONLY a JSON object of this shape:
{
  "ops": [
    {"action": "write", "title": "...", "type": "decision|convention|module|function|architecture",
     "scope": "backend|frontend|shared", "content": "markdown body", "links": {"depends_on": ["memory://..."]},
     "subject_paths": ["src/pkg/file.py"], "subject_symbols": ["pkg.file.func"]},
    {"action": "link", "src": "memory://...", "dst": "memory://...", "relation": "depends_on"}
  ]
}
If there is nothing durable, respond with {"ops": []}.
"""


class Provider(Protocol):
    def complete(self, prompt: str) -> str: ...


class CliProvider:
    """Generic agent-CLI provider: run ANY one-shot CLI completer — claude,
    gemini, codex, a local ``llm``/``ollama``, anything.

    The prompt is substituted into a ``{prompt}`` token if the command has one
    (passed as an argument), otherwise piped on stdin; a ``{model}`` token is
    replaced by ``model``. No API key — it uses whatever the CLI is already
    authenticated with. This is what makes Tremula agent-agnostic rather than
    tied to one vendor.
    """

    def __init__(self, command: list[str], model: str | None = None, timeout: int = 120):
        if not command:
            raise ValueError("CliProvider needs a non-empty command")
        self.command = command
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        argv: list[str] = []
        stdin: str | None = prompt
        for tok in self.command:
            if tok == "{prompt}":
                argv.append(prompt)
                stdin = None  # prompt goes as an arg, not stdin
            elif tok == "{model}":
                argv.append(self.model or "")
            else:
                argv.append(tok)
        # ALWAYS mute Tremula hooks inside the nested agent CLI: it inherits cwd
        # and would otherwise fire this project's hooks itself — the second leg
        # of the fork bomb, regardless of who invoked the provider (distiller,
        # live tests, future callers).
        env = {**os.environ, HOOKS_DISABLED_ENV: "1"}
        try:
            result = subprocess.run(
                argv, input=stdin, capture_output=True, text=True,
                timeout=self.timeout, env=env,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"the `{self.command[0]}` CLI is not on PATH. Tremula's default "
                "provider runs whatever agent CLI you have (no API key needed) — "
                "install one (claude / gemini / codex), or set provider.kind="
                "anthropic with an API key in ~/.tremula/config.yaml."
            ) from exc
        if result.returncode != 0:
            raise RuntimeError(f"{self.command[0]} failed: {result.stderr.strip()}")
        return result.stdout


class ClaudeCliProvider(CliProvider):
    """Back-compat alias: the ``claude -p`` preset (kept so existing callers and
    ``provider.kind='claude-cli'`` keep working; ``auto`` is the new default)."""

    def __init__(self, model: str | None = None, timeout: int = 120):
        cmd = ["claude", "-p", "--output-format", "text"]
        if model:
            cmd += ["--model", model]
        super().__init__(cmd, model=model, timeout=timeout)


class AnthropicProvider:
    """API provider: Anthropic SDK + a chosen model. Needs an API key."""

    def __init__(self, model: str, base_url: str | None, api_key: str):
        from anthropic import Anthropic  # optional dependency

        self.model = model
        self.client = Anthropic(api_key=api_key, base_url=base_url)

    def complete(self, prompt: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")


def _preset_or_raise(agent: str) -> list[str]:
    if agent not in AGENT_PRESETS:
        raise RuntimeError(
            f"unknown agent preset {agent!r}; known: {sorted(AGENT_PRESETS)}. "
            "Use provider.kind='cli' with an explicit command for others."
        )
    return list(AGENT_PRESETS[agent])


def detect_agents() -> list[str]:
    """Known agent CLIs currently on PATH, in preset order. Pure PATH lookup."""
    return [name for name in AGENT_PRESETS if shutil.which(name)]


def _anthropic_or_raise(cfg: ProviderConfig) -> Provider:
    key = os.environ.get(cfg.auth_env)
    if not key:
        raise RuntimeError(f"{cfg.auth_env} is unset; cannot use the anthropic provider")
    return AnthropicProvider(model=cfg.model, base_url=cfg.base_url, api_key=key)


def provider_from_config(cfg: ProviderConfig) -> Provider:
    """Resolve a :class:`Provider` from config — agent-agnostic, no vendor default.

    ``auto`` picks the single agent CLI on PATH (or the one pinned via
    ``agent``), else the Anthropic API if a key is set. ``cli`` runs an explicit
    ``command``/``agent``. ``anthropic`` uses the SDK. ``claude-cli`` is a
    back-compat alias.
    """
    kind = cfg.kind
    if kind == "anthropic":
        return _anthropic_or_raise(cfg)
    if kind == "claude-cli":  # back-compat
        return ClaudeCliProvider(model=cfg.model)
    if kind == "cli":
        command = cfg.command or (_preset_or_raise(cfg.agent) if cfg.agent else None)
        if not command:
            raise RuntimeError(
                "provider.kind='cli' needs `command` (explicit argv) or `agent` "
                f"(one of {sorted(AGENT_PRESETS)})."
            )
        return CliProvider(command, model=cfg.model)
    if kind == "auto":
        if cfg.agent:  # user pinned a specific agent
            return CliProvider(_preset_or_raise(cfg.agent), model=cfg.model)
        found = detect_agents()
        if len(found) == 1:
            return CliProvider(_preset_or_raise(found[0]), model=cfg.model)
        if len(found) > 1:
            raise RuntimeError(
                f"multiple agent CLIs on PATH ({', '.join(found)}); pick one with "
                "provider.agent in ~/.tremula/config.yaml, or use provider.kind="
                "anthropic."
            )
        if os.environ.get(cfg.auth_env):  # no CLI, but a key is present
            return _anthropic_or_raise(cfg)
        raise RuntimeError(
            "no agent CLI found on PATH (claude / gemini / codex) and "
            f"{cfg.auth_env} is unset. Install an agent CLI, or set a provider in "
            "~/.tremula/config.yaml."
        )
    raise ValueError(f"unknown provider kind: {cfg.kind!r}")


FEDERATION_RULE = """\
FEDERATION: this project shares contract vaults (roots) with other projects.
Available roots: {roots}.
If the session shows a cross-service call, or a change to an endpoint / shared
type / event schema that another project depends on, ALSO emit a contract op:
{{"action": "contract", "root": "<one of the roots above>",
  "title": "<endpoint or resource, e.g. POST /items>",
  "role": "provider" | "consumer",
  "content": "markdown describing YOUR side: schema, expectations, behavior"}}
provider = this project implements/serves it; consumer = this project calls it.
You write only your own side's section; the other project maintains theirs.
"""


def build_prompt(
    events: list[dict],
    existing_notes: list[dict] | None = None,
    budget: int = 24000,
    roots: list[str] | None = None,
) -> str:
    # Keep the most recent events within the char budget; old ones age out.
    kept: list[str] = []
    used = 0
    for event in reversed(events):
        line = json.dumps(event, ensure_ascii=False)
        if kept and used + len(line) > budget:
            break
        kept.append(line)
        used += len(line)
    kept.reverse()
    omitted = len(events) - len(kept)
    header = f"({omitted} earlier events omitted)\n" if omitted else ""
    transcript = header + "\n".join(kept)

    existing_block = ""
    if existing_notes:
        existing_block = "EXISTING NOTES (revise by reusing the exact title):\n" + \
            json.dumps(existing_notes, ensure_ascii=False, indent=0) + "\n\n"
    federation_block = ""
    if roots:
        federation_block = FEDERATION_RULE.format(roots=", ".join(sorted(roots))) + "\n"
    return f"{HYGIENE}\n{federation_block}\n{existing_block}SESSION EVENTS:\n{transcript}\n"


JUDGE_PROMPT = """\
ENRICHMENT JUDGE. A human-authored note already exists. The background distiller
proposes new content for it. Decide whether MERGING the proposal improves the
note while losing none of its existing information.

Return ONLY JSON:
{"decision": "enrich" | "reject",
 "merged": "FULL merged markdown body, preserving ALL original content plus the new facts",
 "reason": "one sentence"}

Rules:
- "enrich" only if you can produce a merged body that keeps EVERY fact from the
  ORIGINAL and adds value. The merged body MUST contain all original content.
- "reject" if the proposal is redundant, lower quality, or would drop information.
"""


def _extract_json(text: str) -> dict | None:
    """Best-effort: parse the first {...} object out of an LLM response."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_ops(text: str) -> list[dict]:
    """Extract the ops list from an LLM response (tolerant of surrounding prose)."""
    data = _extract_json(text)
    if not data:
        return []
    ops = data.get("ops", [])
    return ops if isinstance(ops, list) else []


def _significant_words(text: str) -> set[str]:
    # \w is Unicode-aware: the backstop must hold for non-Latin note bodies too
    # (an ASCII-only pattern would see zero words and vacuously pass).
    return set(re.findall(r"\w{3,}", text.lower()))


def content_preserved(original: str, merged: str, threshold: float = 0.85) -> bool:
    """Deterministic no-loss backstop: most of the original's significant words
    must survive in the merged body. Blocks a 'thin replacement' even if the LLM
    judge mistakenly approves it; rephrasing/enrichment passes."""
    orig = _significant_words(original)
    if not orig:
        return True
    kept = orig & _significant_words(merged)
    return len(kept) / len(orig) >= threshold


def judge_enrichment(provider: Provider, original: str, proposed: str) -> dict:
    """Ask the LLM judge whether the proposal enriches the manual note."""
    prompt = f"{JUDGE_PROMPT}\n\nORIGINAL NOTE:\n{original}\n\nPROPOSED CONTENT:\n{proposed}\n"
    try:
        resp = provider.complete(prompt)
    except Exception as exc:  # judge failure must never lose the original
        return {"decision": "reject", "reason": f"judge error: {exc}"}
    verdict = _extract_json(resp)
    if not verdict or verdict.get("decision") not in {"enrich", "reject"}:
        return {"decision": "reject", "reason": "judge returned no clear verdict"}
    return verdict


def _union(existing, new) -> list[str]:
    """Order-preserving union — extend a binding without ever dropping a member."""
    out = list(existing or [])
    for item in (new or []):
        if item not in out:
            out.append(item)
    return out


def _apply_write(vault: VaultService, op: dict, provider: Provider | None,
                 applied: list[str], judge_distilled: bool = False,
                 session_paths: set[str] | None = None) -> None:
    session_paths = session_paths or set()
    title, type_ = op["title"], op.get("type", "module")
    scope, content, links = op.get("scope", "shared"), op.get("content", ""), op.get("links")
    uri = vault.target_uri(title, type_)
    try:
        # track=False: a collision check is machinery, not usage — it must not
        # inflate heat telemetry (the stale detector would read it as demand).
        original_note = vault.read_note(uri, track=False)
    except (FileNotFoundError, MemoryURIError):
        original_note = None

    # Subject binding for this write: keep only LLM-emitted paths actually seen
    # this session (drops hallucinated paths); symbols pass through unfiltered.
    new_paths = [p for p in (op.get("subject_paths") or [])
                 if isinstance(p, str) and p in session_paths]
    new_symbols = [s for s in (op.get("subject_symbols") or []) if isinstance(s, str)]

    # Judge an update when the target is human-authored (always) or when it is
    # the distiller's own note and the user opted into judging those too.
    needs_judge = original_note is not None and (
        original_note["source"] != "distilled" or judge_distilled
    )
    if not needs_judge:
        if original_note is None:
            # Brand-new distilled note: born provisional with its subject binding.
            status, count = "provisional", 0
            paths, symbols = new_paths, new_symbols
        else:
            # Updating the distiller's own note: preserve the monotonic lifecycle
            # (never reset count/status on a re-distill) and extend the binding.
            status = original_note["status"]
            count = original_note["confirmation_count"]
            paths = _union(original_note.get("subject_paths"), new_paths)
            symbols = _union(original_note.get("subject_symbols"), new_symbols)
        uri = vault.write_note(title=title, content=content, type=type_, scope=scope,
                               links=links, source="distilled", protect=True,
                               status=status, confirmation_count=count,
                               subject_paths=paths, subject_symbols=symbols)
        applied.append(f"write {uri}")
        return

    if provider is None:
        applied.append(f"skip write {uri}: existing note, no judge available")
        return
    original = original_note["body"]
    verdict = judge_enrichment(provider, original, content)
    if verdict.get("decision") != "enrich":
        applied.append(f"skip enrich {uri}: {verdict.get('reason', 'rejected')}")
        return
    merged = verdict.get("merged") or content
    if not content_preserved(original, merged):
        applied.append(f"skip enrich {uri}: backstop blocked content loss")
        return
    # Apply the judged merge. The note keeps its provenance (a manual note
    # stays human-owned; a distilled note stays distilled) and its original
    # type/scope and frontmatter links — enrichment adds, it never strips
    # metadata. Proposed links are unioned in.
    merged_links = {rel: list(targets) for rel, targets in original_note["links"].items()}
    for rel, targets in (links or {}).items():
        bucket = merged_links.setdefault(rel, [])
        for target in targets:
            if target not in bucket:
                bucket.append(target)
    vault.write_note(
        title=title, content=merged,
        type=original_note["type"], scope=original_note["scope"],
        links=merged_links, source=original_note["source"], protect=False,
        # Enrichment is content-only: preserve the note's lifecycle + binding.
        status=original_note["status"],
        confirmation_count=original_note["confirmation_count"],
        subject_paths=_union(original_note.get("subject_paths"), new_paths),
        subject_symbols=_union(original_note.get("subject_symbols"), new_symbols),
    )
    applied.append(f"enrich {uri}: {verdict.get('reason', '')}".rstrip())


def apply_ops(vault: VaultService, ops: list[dict], provider: Provider | None = None,
              judge_distilled: bool = False, session_paths: set[str] | None = None) -> list[str]:
    """Apply note operations; returns a log of what changed. Bad ops are skipped.

    Writes that collide with a human-authored note are routed through the LLM
    judge (``provider``) which decides enrich vs reject, guarded by a no-loss
    backstop. With ``judge_distilled``, updates to the distiller's own notes
    take the same judged path instead of a free overwrite. ``session_paths``
    validates new notes' subject bindings against files actually touched."""
    applied: list[str] = []
    for op in ops:
        action = op.get("action")
        try:
            if action == "write":
                _apply_write(vault, op, provider, applied, judge_distilled=judge_distilled,
                             session_paths=session_paths)
            elif action == "link":
                vault.link_notes(op["src"], op["dst"], op["relation"])
                applied.append(f"link {op['src']} -{op['relation']}-> {op['dst']}")
            elif action == "contract":
                from .contracts import upsert_contract_section  # avoid module cycle

                uri = upsert_contract_section(
                    vault, root_key=op["root"], title=op["title"],
                    project=vault.project or "unknown", role=op["role"],
                    content=op.get("content", ""),
                )
                applied.append(f"contract {uri} [{op['role']}]")
            else:
                applied.append(f"skip unknown action: {action!r}")
        except (KeyError, ValueError, FileNotFoundError) as exc:
            applied.append(f"skip {action}: {exc}")
    return applied


def distill(events: list[dict], vault: VaultService, provider: Provider,
            prompt_budget: int = 24000, judge_distilled: bool = False,
            session_paths: set[str] | None = None) -> list[str]:
    """Run one distillation pass: events -> LLM -> applied note operations."""
    if not events:
        return []
    existing = vault.existing_notes()
    # Member roots = everything mounted besides the project's own ramet.
    roots = sorted(k for k in vault.mounts if k != vault.project)
    response = provider.complete(
        build_prompt(events, existing, budget=prompt_budget, roots=roots)
    )
    ops = parse_ops(response)
    return apply_ops(vault, ops, provider=provider, judge_distilled=judge_distilled,
                     session_paths=session_paths)


# ---- working-tree confirmation -----------------------------------------------
#
# A distilled note is born ``provisional``. On each distill run a BOUNDED pass
# re-checks provisional notes: if a note's subject code is observed present in
# the working tree, its monotonic confirmation counter is bumped; at the
# threshold it becomes ``ratified``. This is injection-scope only — it never
# deletes a note and never lowers a count (absence is not deletion; a plain
# branch switch must not erode trust). Real removal is the explicit
# user-invoked ``tremula verify`` pass.


def _check_confirmation(note: dict, repo_root: Path, session_paths: set[str]) -> bool:
    """Per-type predicate: is this note's subject code present right now?"""
    type_ = note["type"]
    paths = note.get("subject_paths") or []
    symbols = note.get("subject_symbols") or []
    if type_ in ("function", "module"):
        present = [p for p in paths if (repo_root / p).is_file()]
        if not present:
            return False
        if not symbols:
            return True  # path-only (no symbols recorded or no tree-sitter grammar)
        from .astmap import resolve_symbol
        return any(resolve_symbol(repo_root, p, sym) for p in present for sym in symbols)
    if type_ == "convention":
        # Marker present (coarse: any declared subject file exists). Refinable.
        return bool(paths) and any((repo_root / p).is_file() for p in paths)
    if type_ in ("decision", "architecture"):
        # Re-observation: a subject path was touched in this session.
        return bool(set(paths) & set(session_paths))
    # contract / index / other: not auto-confirmed (born ratified).
    return False


def _confirm_notes(vault: VaultService, repo_root: str | Path,
                   session_paths: set[str], settings) -> list[str]:
    """Bounded background confirmation pass — see section header."""
    log: list[str] = []
    repo_root = Path(repo_root)
    for row in vault.index.provisional_notes(limit=settings.confirmation_batch_size):
        uri = row["uri"]
        try:
            note = vault.read_note(uri, track=False)
        except (MemoryURIError, FileNotFoundError):
            continue
        if note["source"] != "distilled":
            continue  # never touch human-authored notes (distiller-safety)
        if not _check_confirmation(note, repo_root, session_paths):
            continue
        new_count = note["confirmation_count"] + 1
        ratified = new_count >= settings.confirmation_threshold
        vault.write_note(
            title=note["title"], content=note["body"],
            type=note["type"], scope=note["scope"], links=note["links"],
            source="distilled", protect=False,
            status="ratified" if ratified else "provisional",
            confirmation_count=new_count,
            subject_paths=note["subject_paths"], subject_symbols=note["subject_symbols"],
        )
        log.append(f"confirm {uri} count={new_count}"
                   + (" -> ratified" if ratified else ""))
    return log


def _session_paths(session_file, events: list[dict], repo_root) -> set[str]:
    """Reference set that validates note subject bindings. Deliberately broad —
    the current event slice, the FULL session (offset 0), and the working tree's
    changed files — so a note born from a late event slice still binds to code
    touched earlier in the session (whose events a prior run already consumed)."""
    from .capture import read_session
    from .workctx import extract_paths_from_events, git_changed_files

    paths = set(extract_paths_from_events(events, max_paths=200))
    try:
        paths |= set(extract_paths_from_events(read_session(session_file), max_paths=400))
    except Exception:
        pass
    if repo_root is not None:
        paths |= set(git_changed_files(repo_root))
    return paths


# ---- incremental scheduling --------------------------------------------------
#
# Claude Code fires Stop after EVERY assistant turn. Distilling the whole
# session on each turn would mean one claude -p call per turn, overlapping runs,
# and re-distilling the same events repeatedly. Three mechanisms bound it:
# a byte-offset sidecar (each run consumes only NEW events), a pid lockfile
# (never two distillers per session), and a minimum interval for Stop
# (PreCompact/SessionEnd flush regardless of the interval).

FLUSH_TRIGGERS = {"PreCompact", "SessionEnd"}


def _state_path(session_file: str | Path) -> Path:
    return Path(session_file).with_suffix(".distill.json")


def _lock_path(session_file: str | Path) -> Path:
    return Path(session_file).with_suffix(".distill.lock")


def load_distill_state(session_file: str | Path) -> dict:
    try:
        return json.loads(_state_path(session_file).read_text())
    except (OSError, json.JSONDecodeError):
        return {"offset": 0, "last_run": 0.0}


def save_distill_state(session_file: str | Path, offset: int, last_run: float) -> None:
    _state_path(session_file).write_text(
        json.dumps({"offset": offset, "last_run": last_run})
    )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, ValueError):
        return False


def acquire_path_lock(lock: Path) -> bool:
    """Take a pid lockfile; break it only if the holder process is dead."""
    for _ in range(2):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                holder = int(lock.read_text().strip() or "0")
            except (OSError, ValueError):
                holder = 0
            if holder and _pid_alive(holder):
                return False
            lock.unlink(missing_ok=True)  # stale lock from a dead process
    return False


def release_path_lock(lock: Path) -> None:
    lock.unlink(missing_ok=True)


def acquire_lock(session_file: str | Path) -> bool:
    """Take the per-session distill lock; break it only if the holder is dead."""
    return acquire_path_lock(_lock_path(session_file))


def release_lock(session_file: str | Path) -> None:
    release_path_lock(_lock_path(session_file))


def should_distill(
    session_file: str | Path,
    trigger: str = "Stop",
    min_interval: float = 600.0,
    now: float | None = None,
) -> tuple[bool, str]:
    """Cheap hook-side decision: is spawning a distiller worth a process?"""
    path = Path(session_file)
    if not path.exists():
        return False, "no session file"
    state = load_distill_state(session_file)
    if path.stat().st_size <= state.get("offset", 0):
        return False, "no new events"
    lock = _lock_path(session_file)
    if lock.exists():
        try:
            holder = int(lock.read_text().strip() or "0")
        except (OSError, ValueError):
            holder = 0
        if holder and _pid_alive(holder):
            return False, "distill already in flight"
    if trigger not in FLUSH_TRIGGERS:
        now = time.time() if now is None else now
        if now - state.get("last_run", 0.0) < min_interval:
            return False, "debounced (min interval not reached)"
    return True, "ok"


def run_distill(
    session_file: str | Path,
    vault: VaultService,
    provider: Provider,
    trigger: str = "Stop",
    prompt_budget: int = 24000,
    judge_distilled: bool = False,
    repo_root: str | Path | None = None,
) -> list[str]:
    """Worker entry: lock, consume new events from the offset, distill, advance.

    ``repo_root`` (the code repo, not the vault) enables the working-tree
    confirmation pass and subject-path validation. Without it both degrade
    gracefully: notes still distill, bindings just bind against session events
    alone and no confirmations accrue.
    """
    from .capture import read_session_since  # local import to avoid a cycle

    if not acquire_lock(session_file):
        return ["skip: distill already in flight"]
    try:
        state = load_distill_state(session_file)
        events, new_offset = read_session_since(session_file, state.get("offset", 0))
        if not events:
            return []
        session_paths = _session_paths(session_file, events, repo_root)
        applied = distill(events, vault, provider, prompt_budget=prompt_budget,
                          judge_distilled=judge_distilled, session_paths=session_paths)
        save_distill_state(session_file, offset=new_offset, last_run=time.time())
        # Every Nth productive run, append a revision pass (split/merge/archive).
        from .revise import bump_and_maybe_revise

        applied += bump_and_maybe_revise(vault, provider)
        # Background confirmation pass: ratify provisional notes whose subject
        # code is present. Needs the code repo root; skipped gracefully without it.
        if repo_root is not None:
            applied += _confirm_notes(vault, repo_root, session_paths, load_settings())
        if applied and vault.project and vault.project in vault.mounts:
            # New notes must surface in _index.md without waiting for a human:
            # deterministic auto-section sync (no LLM near the index).
            from .index_md import sync_index_auto_section

            sync_index_auto_section(vault.mounts[vault.project], vault.project)
        return applied
    finally:
        release_lock(session_file)
