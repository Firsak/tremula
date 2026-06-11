"""Self-organization (Stage 7): split oversized notes, merge duplicates,
archive stale ones.

Principles, learned from hand-curating the dogfood vault:
- Deterministic candidate detection; the LLM only CONFIRMS (merge? still
  useful?). Asking a model to "find problems" breeds the noise this pass exists
  to remove.
- Auto-apply touches ``source: distilled`` notes only. Manual notes get at most
  a suggestion line in the log.
- Archive, never delete: cold notes move to ``attic/`` inside their vault —
  excluded from index/search/injection, browsable for recovery; git history is
  the deeper tombstone.
"""

from __future__ import annotations

import datetime
import json
import re
import time
from pathlib import Path

import frontmatter

from .config import Settings, load_settings, tremula_home
from .distiller import Provider, _extract_json, content_preserved
from .index_md import sync_index_auto_section
from .memory_uri import MemoryURI, MemoryURIError, resolve
from .vault import VaultService

MERGE_PROMPT = """\
DUPLICATE JUDGE. Two notes may describe the same thing. If they do, produce ONE
merged body that preserves EVERY fact from BOTH. If they are genuinely about
different things, reject.

Return ONLY JSON:
{"merge": true | false,
 "content": "full merged markdown body (only when merge=true)",
 "reason": "one sentence"}
"""

STALE_PROMPT = """\
STALE JUDGE. These notes are cold: never read, nothing links to them, old.
Confirm which are safe to ARCHIVE (moved to attic/, recoverable — not deleted).
Keep anything that still looks like durable, load-bearing knowledge.

Return ONLY JSON: {"archive": ["<uri>", ...], "reason": "one sentence"}
"""

_EXEMPT_TYPES = {"index", "contract"}  # contracts are shared: one side's heat lies


# ---- candidate detection (deterministic) ---------------------------------------

def _all_notes(vault: VaultService) -> list[dict]:
    notes = []
    for row in vault.index.all_notes():
        try:
            note = vault.read_note(row["uri"], track=False)
        except (MemoryURIError, FileNotFoundError):
            continue
        note["reads"] = row["reads"]
        note["mtime"] = row["mtime"]
        notes.append(note)
    return notes


def _inbound_count(vault: VaultService, uri: str) -> int:
    row = vault.index.conn.execute(
        "SELECT COUNT(*) AS n FROM links WHERE dst = ?", (uri,)
    ).fetchone()
    return row["n"]


def find_oversized(vault: VaultService, max_chars: int) -> list[dict]:
    return [n for n in _all_notes(vault)
            if len(n["body"]) > max_chars and n["type"] not in _EXEMPT_TYPES]


def _title_tokens(title: str) -> set[str]:
    return {t for t in re.findall(r"\w{4,}", title.lower())
            if t not in {"module", "decision", "convention", "function", "note"}}


def _head_tokens(title: str) -> set[str]:
    """The identity-bearing tokens of a title.

    For dotted names (``tremula.config.hooks_disabled``) only the LAST segment
    identifies the thing — parent segments are shared by every sibling and
    must not make siblings look like duplicates of each other.
    """
    if "." in title and " " not in title:
        return _title_tokens(title.rsplit(".", 1)[-1])
    return _title_tokens(title)


def find_duplicate_candidates(vault: VaultService) -> list[tuple[dict, dict]]:
    """Same-type distilled note pairs whose titles share DISCRIMINATIVE tokens.

    A token carried by many titles (e.g. the package prefix ``tremula`` in
    every dotted module name) says nothing about duplication — only tokens
    rare across the vault count as a signal. Without this, every ``pkg.*``
    module pairs with every other (observed live on the dogfood vault).
    """
    distilled = [n for n in _all_notes(vault)
                 if n["source"] == "distilled" and n["type"] not in _EXEMPT_TYPES]
    tokens = {n["uri"]: _title_tokens(n["title"]) for n in distilled}
    # Document frequency across distilled titles; ubiquitous tokens are noise.
    freq: dict[str, int] = {}
    for toks in tokens.values():
        for tok in toks:
            freq[tok] = freq.get(tok, 0) + 1
    common_cutoff = max(3, len(distilled) * 0.3)
    discriminative = {t for t, n in freq.items() if n < common_cutoff}

    pairs: list[tuple[dict, dict]] = []
    for i, a in enumerate(distilled):
        ta = tokens[a["uri"]] & discriminative
        for b in distilled[i + 1:]:
            if b["type"] != a["type"]:
                continue
            tb = tokens[b["uri"]] & discriminative
            shared = ta & tb
            # Weak signal (one shared token) only counts when that token is the
            # HEAD of both titles — sibling functions sharing a module segment
            # are not duplicates of each other.
            weak = shared & _head_tokens(a["title"]) & _head_tokens(b["title"])
            if len(shared) >= 2 or (weak and min(len(ta), len(tb)) <= 2):
                pairs.append((a, b))
    return pairs


def find_stale(vault: VaultService, now: float, stale_after_days: int) -> list[dict]:
    """Distilled + never read + nothing links to it + old = archive candidate."""
    cutoff = now - stale_after_days * 86400
    out = []
    for note in _all_notes(vault):
        if note["source"] != "distilled" or note["type"] in _EXEMPT_TYPES:
            continue
        if note["reads"] == 0 and note["mtime"] < cutoff \
                and _inbound_count(vault, note["uri"]) == 0:
            out.append(note)
    return out


# ---- mutations -------------------------------------------------------------------

def archive_note(vault: VaultService, uri: str, reason: str) -> Path:
    """Move a note into its vault's ``attic/`` and drop it from the index."""
    parsed = MemoryURI.parse(uri)
    path = resolve(parsed, vault.mounts)
    vault_root = Path(vault.mounts[parsed.project])
    target = vault_root / "attic" / path.relative_to(vault_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.load(path)
    post.metadata["archived"] = datetime.date.today().isoformat()
    post.metadata["archive_reason"] = reason
    target.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    path.unlink()
    vault.index.delete_note(uri)
    return target


def rewrite_inbound_links(vault: VaultService, old_uri: str, new_uri: str) -> int:
    """Point every frontmatter link aimed at ``old_uri`` to ``new_uri``."""
    rows = vault.index.conn.execute(
        "SELECT DISTINCT src FROM links WHERE dst = ?", (old_uri,)
    ).fetchall()
    changed = 0
    for row in rows:
        src = MemoryURI.parse(row["src"])
        path = resolve(src, vault.mounts)
        if not path.exists():
            continue
        post = frontmatter.load(path)
        touched = False
        for key, value in list(post.metadata.items()):
            targets = value if isinstance(value, list) else [value]
            if old_uri in targets:
                replaced = [new_uri if t == old_uri else t for t in targets]
                deduped = list(dict.fromkeys(replaced))
                post.metadata[key] = deduped
                touched = True
        if touched:
            path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
            changed += 1
    if changed:
        vault.index.refresh(vault.mounts)
    return changed


def _merge_pair(vault: VaultService, provider: Provider, a: dict, b: dict,
                log: list[str]) -> None:
    # Survivor = the better-anchored note (inbound links, then heat).
    def weight(n: dict) -> tuple[int, int]:
        return (_inbound_count(vault, n["uri"]), n["reads"])

    survivor, loser = (a, b) if weight(a) >= weight(b) else (b, a)
    prompt = (f"{MERGE_PROMPT}\nNOTE A ({survivor['uri']}):\n{survivor['body']}\n\n"
              f"NOTE B ({loser['uri']}):\n{loser['body']}\n")
    try:
        verdict = _extract_json(provider.complete(prompt)) or {}
    except Exception as exc:
        log.append(f"skip merge {loser['uri']}: judge error: {exc}")
        return
    if not verdict.get("merge") or not verdict.get("content"):
        log.append(f"keep both {survivor['uri']} / {loser['uri']}: "
                   f"{verdict.get('reason', 'not duplicates')}")
        return
    merged = str(verdict["content"])
    if not (content_preserved(survivor["body"], merged, 0.8)
            and content_preserved(loser["body"], merged, 0.8)):
        log.append(f"skip merge {loser['uri']}: backstop blocked content loss")
        return
    links: dict[str, list[str]] = {}
    for note in (survivor, loser):
        for rel, targets in note["links"].items():
            bucket = links.setdefault(rel, [])
            bucket += [t for t in targets if t not in bucket and t != loser["uri"]]
    # Write to the survivor's RESOLVED path, not via write_note(title=...):
    # a body's H1 (where titles come from) may not match the file's slug, and
    # the merged content must land in the survivor's file, never a third one.
    survivor_path = resolve(MemoryURI.parse(survivor["uri"]), vault.mounts)
    post = frontmatter.Post(merged, type=survivor["type"], scope=survivor["scope"],
                            source="distilled", **links)
    survivor_path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    vault.index.refresh(vault.mounts)
    rewired = rewrite_inbound_links(vault, loser["uri"], survivor["uri"])
    archive_note(vault, loser["uri"], reason=f"merged into {survivor['uri']}")
    log.append(f"merge {loser['uri']} -> {survivor['uri']} "
               f"({rewired} inbound links rewritten)")


# ---- the pass ----------------------------------------------------------------------

def revise(vault: VaultService, provider: Provider | None, settings: Settings,
           dry_run: bool = False, now: float | None = None) -> list[str]:
    """One revision pass; returns a log. ``dry_run`` lists candidates only."""
    now = time.time() if now is None else now
    log: list[str] = ["revision pass" + (" (dry-run)" if dry_run else "")]

    # 1) oversized -> deterministic split (distilled only; manual = suggestion)
    for note in find_oversized(vault, settings.max_note_chars):
        if note["source"] != "distilled":
            log.append(f"suggest split {note['uri']}: oversized manual note "
                       f"({len(note['body'])} chars) — split by hand or via split_note")
            continue
        if dry_run:
            log.append(f"would split {note['uri']} ({len(note['body'])} chars)")
            continue
        children = vault.split_note(note["uri"])
        log.append(f"split {note['uri']} -> {len(children)} children"
                   if children else f"skip split {note['uri']}: no ## sections")

    # 2) duplicates -> judged merge (bounded LLM cost)
    pairs = find_duplicate_candidates(vault)[: settings.revision_max_merges]
    for a, b in pairs:
        if dry_run:
            log.append(f"would judge merge: {a['uri']} ~ {b['uri']}")
        elif provider is None:
            log.append(f"skip merge {a['uri']} ~ {b['uri']}: no provider")
        else:
            _merge_pair(vault, provider, a, b, log)

    # 3) stale -> batched confirm -> attic
    stale = find_stale(vault, now, settings.stale_after_days)
    if stale:
        if dry_run:
            log += [f"would archive (cold): {n['uri']}" for n in stale]
        elif provider is None:
            log.append("skip stale check: no provider")
        else:
            listing = "\n\n".join(f"<{n['uri']}>\n{n['body'][:600]}" for n in stale)
            try:
                verdict = _extract_json(
                    provider.complete(f"{STALE_PROMPT}\n{listing}\n")) or {}
            except Exception as exc:
                verdict = {}
                log.append(f"skip stale check: judge error: {exc}")
            confirmed = set(verdict.get("archive", []))
            for note in stale:
                if note["uri"] in confirmed:
                    archive_note(vault, note["uri"],
                                 reason=verdict.get("reason", "stale"))
                    log.append(f"archive {note['uri']}")
                else:
                    log.append(f"keep {note['uri']}: not confirmed stale")

    if not dry_run and vault.project and vault.project in vault.mounts:
        sync_index_auto_section(vault.mounts[vault.project], vault.project)
    return log


# ---- distill-run counter (trigger) ---------------------------------------------------

def _counter_path(project: str) -> Path:
    return tremula_home() / "index" / f"{project}.revision.json"


def bump_and_maybe_revise(vault: VaultService, provider: Provider | None) -> list[str]:
    """Called by the distill worker after each productive run: every Nth run
    appends a revision pass. Failures never break the distill itself."""
    project = vault.project
    if not project:
        return []
    try:
        settings = load_settings()
        path = _counter_path(project)
        try:
            runs = json.loads(path.read_text()).get("runs", 0)
        except (OSError, json.JSONDecodeError):
            runs = 0
        runs += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"runs": runs}))
        if runs % max(1, settings.revision_every_n_runs) != 0:
            return []
        return revise(vault, provider, settings)
    except Exception as exc:
        return [f"revision error: {exc}"]
