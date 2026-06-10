"""The distiller: turn a captured session into durable notes via an LLM.

Runs in a detached process (off the hot path). The LLM provider is abstracted
(``claude -p`` by default; Anthropic API or a local OpenAI-compatible endpoint
by config) so swapping it is one setting. The provider is injectable, so tests
drive distillation with a deterministic fake instead of a live model.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Protocol

from .config import ProviderConfig
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

Respond with ONLY a JSON object of this shape:
{
  "ops": [
    {"action": "write", "title": "...", "type": "decision|convention|module|function|architecture",
     "scope": "backend|frontend|shared", "content": "markdown body", "links": {"depends_on": ["memory://..."]}},
    {"action": "link", "src": "memory://...", "dst": "memory://...", "relation": "depends_on"}
  ]
}
If there is nothing durable, respond with {"ops": []}.
"""


class Provider(Protocol):
    def complete(self, prompt: str) -> str: ...


class ClaudeCliProvider:
    """Default provider: shells out to ``claude -p`` (uses the user's subscription)."""

    def __init__(self, model: str | None = None, timeout: int = 120):
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        cmd = ["claude", "-p", "--output-format", "text"]
        if self.model:
            cmd += ["--model", self.model]
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude -p failed: {result.stderr.strip()}")
        return result.stdout


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


def provider_from_config(cfg: ProviderConfig) -> Provider:
    if cfg.kind == "claude-cli":
        return ClaudeCliProvider(model=cfg.model)
    if cfg.kind == "anthropic":
        import os

        key = os.environ.get(cfg.auth_env)
        if not key:
            raise RuntimeError(f"{cfg.auth_env} is unset; cannot use the anthropic provider")
        return AnthropicProvider(model=cfg.model, base_url=cfg.base_url, api_key=key)
    raise ValueError(f"unknown provider kind: {cfg.kind!r}")


def build_prompt(events: list[dict], existing_notes: list[dict] | None = None) -> str:
    transcript = json.dumps(events, ensure_ascii=False, indent=0)
    existing_block = ""
    if existing_notes:
        existing_block = "EXISTING NOTES (revise by reusing the exact title):\n" + \
            json.dumps(existing_notes, ensure_ascii=False, indent=0) + "\n\n"
    return f"{HYGIENE}\n\n{existing_block}SESSION EVENTS:\n{transcript}\n"


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
    return set(re.findall(r"[a-zA-Z0-9_]{3,}", text.lower()))


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


def _apply_write(vault: VaultService, op: dict, provider: Provider | None,
                 applied: list[str]) -> None:
    title, type_ = op["title"], op.get("type", "module")
    scope, content, links = op.get("scope", "shared"), op.get("content", ""), op.get("links")
    try:
        uri = vault.write_note(title=title, content=content, type=type_, scope=scope,
                               links=links, source="distilled", protect=True)
        applied.append(f"write {uri}")
        return
    except PermissionError:
        pass  # collided with a manual note -> reason about enriching it

    uri = vault.target_uri(title, type_)
    if provider is None:
        applied.append(f"skip write {uri}: manual note, no judge available")
        return
    original = vault.read_note(uri)["body"]
    verdict = judge_enrichment(provider, original, content)
    if verdict.get("decision") != "enrich":
        applied.append(f"skip enrich {uri}: {verdict.get('reason', 'rejected')}")
        return
    merged = verdict.get("merged") or content
    if not content_preserved(original, merged):
        applied.append(f"skip enrich {uri}: backstop blocked content loss")
        return
    # Apply the judged merge; the note stays human-owned (source=manual).
    vault.write_note(title=title, content=merged, type=type_, scope=scope,
                     links=links, source="manual", protect=False)
    applied.append(f"enrich {uri}: {verdict.get('reason', '')}".rstrip())


def apply_ops(vault: VaultService, ops: list[dict], provider: Provider | None = None) -> list[str]:
    """Apply note operations; returns a log of what changed. Bad ops are skipped.

    Writes that collide with a human-authored note are routed through the LLM
    judge (``provider``) which decides enrich vs reject, guarded by a no-loss
    backstop."""
    applied: list[str] = []
    for op in ops:
        action = op.get("action")
        try:
            if action == "write":
                _apply_write(vault, op, provider, applied)
            elif action == "link":
                vault.link_notes(op["src"], op["dst"], op["relation"])
                applied.append(f"link {op['src']} -{op['relation']}-> {op['dst']}")
            else:
                applied.append(f"skip unknown action: {action!r}")
        except (KeyError, ValueError, FileNotFoundError) as exc:
            applied.append(f"skip {action}: {exc}")
    return applied


def distill(events: list[dict], vault: VaultService, provider: Provider) -> list[str]:
    """Run one distillation pass: events -> LLM -> applied note operations."""
    if not events:
        return []
    existing = vault.existing_notes()
    response = provider.complete(build_prompt(events, existing))
    ops = parse_ops(response)
    return apply_ops(vault, ops, provider=provider)
