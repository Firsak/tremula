"""Bootstrap: generate the initial vault from a codebase (``tremula bootstrap``).

Pipeline: scan -> tree-sitter AST map -> per-module LLM summaries (prose only;
links come deterministically from the import graph) -> one batched call for key
functions -> a conventions/decisions pass through the distiller's ops pipeline
(inheriting every protection) -> draft root contracts for detected external
calls -> _index auto-section sync + index rebuild.

Everything written carries ``source: distilled`` and ``protect=True``: re-runs
update bootstrap's own notes idempotently (titles are deterministic), and a
hand-written note with a colliding title is skipped, never clobbered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .astmap import FileMap, import_graph, map_file, scan
from .config import Settings
from .distiller import Provider, _extract_json, apply_ops
from .index_md import sync_index_auto_section
from .registry import Registry
from .vault import VaultService

MODULE_PROMPT = """\
MODULE SUMMARY. Summarize ONE source module for a codebase knowledge vault.
Respond with ONLY JSON:
{"purpose": "1-3 sentences: what this module is for",
 "public_api": [{"signature": "name(args)", "description": "one line"}]}
Cover only the most important public symbols (max 8). No marketing language.
"""

FUNCTIONS_PROMPT = """\
FUNCTION SUMMARIES. For each listed function, one durable sentence on what it
does and when to use it. Respond with ONLY JSON:
{"functions": [{"name": "...", "summary": "..."}]}
"""

CONVENTIONS_PROMPT = """\
CONVENTIONS PASS. From the project configuration and layout below, extract the
project's conventions (style, naming, tooling, structure) and any visible
architectural decisions. Same hygiene as always: durable knowledge only, one
note = one atomic fact, no ephemera.

Respond with ONLY a JSON object:
{"ops": [{"action": "write", "title": "...", "type": "convention|decision",
          "scope": "shared", "content": "markdown body"}]}
Maximum 5 ops. If nothing is worth keeping, {"ops": []}.
"""

_URL_RE = re.compile(r"https?://[A-Za-z0-9._-]+(?:/[A-Za-z0-9._/-]*)?")
_HTTP_HINT_RE = re.compile(
    r"\b(requests\.(get|post|put|patch|delete)|fetch\(|axios\.|httpx\.)", re.IGNORECASE
)


@dataclass
class BootstrapPlan:
    repo_root: Path
    modules: list[FileMap] = field(default_factory=list)
    graph: dict[str, list[str]] = field(default_factory=dict)
    functions: list[tuple[FileMap, str, int]] = field(default_factory=list)  # (file, fn, refs)
    external_calls: list[tuple[str, str]] = field(default_factory=list)  # (dotted, url)
    focused: bool = False  # user targeted specific modules (skip project-wide passes)

    def describe(self) -> list[str]:
        lines = [f"bootstrap plan for {self.repo_root}",
                 f"  modules ({len(self.modules)}):"]
        lines += [f"    {m.dotted}  [{m.language}, {m.loc} loc, "
                  f"deps: {', '.join(self.graph.get(m.dotted, [])) or '-'}]"
                  for m in self.modules]
        lines.append(f"  key functions ({len(self.functions)}):")
        lines += [f"    {f.dotted}.{name}  (referenced in {refs} files)"
                  for f, name, refs in self.functions]
        lines.append(f"  external calls ({len(self.external_calls)}):")
        lines += [f"    {dotted}: {url}" for dotted, url in self.external_calls]
        lines.append(f"  LLM calls needed: {len(self.modules)} module + "
                     f"{1 if self.functions else 0} functions + 1 conventions")
        return lines


def _matches_target(fmap: FileMap, target: str) -> bool:
    """Does a module match a user focus target (path, directory, or dotted name)?"""
    target = target.rstrip("/")
    posix = fmap.path.as_posix()
    return (
        fmap.dotted == target
        or fmap.dotted.startswith(target + ".")
        or posix == target
        or posix.startswith(target + "/")
        or posix == target + fmap.path.suffix
    )


def plan_bootstrap(repo_root: str | Path, max_modules: int = 40,
                   max_functions: int = 10,
                   only: list[str] | None = None) -> BootstrapPlan:
    """Deterministic planning pass — no LLM, no writes.

    ``only`` focuses the plan on user-chosen targets (file paths, directories,
    or dotted module names): only matching modules are summarized/stubbed,
    while reference counting still sees the whole project.
    """
    repo_root = Path(repo_root)
    files = [map_file(repo_root, rel) for rel in scan(repo_root)]
    files = [f for f in files if f.loc > 2]  # skip empty stubs
    files.sort(key=lambda f: -f.loc)
    # The graph spans the whole project: a focused run still links its notes to
    # unselected modules (their notes may exist as stubs, or arrive later —
    # links-before-targets is allowed by design).
    graph = import_graph(files)

    modules = files
    if only:
        modules = [f for f in files if any(_matches_target(f, t) for t in only)]
    modules = modules[:max_modules]

    # Key functions: exported, defined in a SELECTED module, and referenced
    # from other project files (counted across the whole project).
    candidates: list[tuple[FileMap, str, int]] = []
    for fmap in modules:
        for sym in fmap.symbols:
            if sym.kind != "function" or not sym.exported:
                continue
            pattern = re.compile(rf"\b{re.escape(sym.name)}\b")
            refs = sum(1 for other in files
                       if other is not fmap and pattern.search(other.source))
            if refs:
                candidates.append((fmap, sym.name, refs))
    candidates.sort(key=lambda c: -c[2])

    external: list[tuple[str, str]] = []
    for fmap in modules:
        if _HTTP_HINT_RE.search(fmap.source):
            for url in _URL_RE.findall(fmap.source):
                if (fmap.dotted, url) not in external:
                    external.append((fmap.dotted, url))

    return BootstrapPlan(repo_root=repo_root, modules=modules, graph=graph,
                         functions=candidates[:max_functions], external_calls=external,
                         focused=bool(only))


def _module_uri(vault: VaultService, dotted: str) -> str:
    return vault.target_uri(dotted, "module")


BRIEF_STUB_MARKER = "(brief bootstrap stub — enriched ambiently as the project is worked on)"


def _render_brief_body(fmap) -> str:
    """Zero-LLM module stub: docstring (if any) + AST symbol listing.

    Big repos can't afford one LLM call per module up front; a stub gives the
    retrieval funnel something to attach immediately, and the ambient distiller
    enriches exactly the modules the user actually works on (it sees existing
    notes and updates its own in place).
    """
    summary = fmap.docstring.split("\n\n")[0].strip() if fmap.docstring \
        else BRIEF_STUB_MARKER
    lines = [f"# {fmap.dotted}", "", summary]
    exported = [s for s in fmap.symbols if s.exported]
    if exported:
        lines += ["", "## Public symbols"]
        lines += [f"- `{s.name}` ({s.kind})" for s in exported[:15]]
    return "\n".join(lines) + "\n"


def _render_module_body(dotted: str, data: dict) -> str:
    lines = [f"# {dotted}", "", str(data.get("purpose", "")).strip()]
    api = data.get("public_api") or []
    if api:
        lines += ["", "## Public API"]
        for entry in api[:8]:
            sig = str(entry.get("signature", "")).strip()
            desc = str(entry.get("description", "")).strip()
            lines.append(f"- `{sig}` — {desc}")
    return "\n".join(lines) + "\n"


def run_bootstrap(
    vault: VaultService,
    provider: Provider | None,
    plan: BootstrapPlan,
    settings: Settings,
    registry: Registry | None = None,
    dry_run: bool = False,
    judge_distilled: bool = False,
    brief: bool = False,
) -> list[str]:
    """Execute the plan; returns a human-readable log.

    ``dry_run`` -> plan only. ``brief`` -> ZERO LLM calls: module stubs from
    docstrings + AST symbols (links still graph-derived); function and
    conventions passes are skipped — the ambient distiller enriches the stubs
    progressively as the user works on each module.
    """
    log: list[str] = list(plan.describe())
    if dry_run:
        log.append("dry-run: no LLM calls, nothing written")
        return log
    if provider is None and not brief:
        raise ValueError("a provider is required unless dry_run or brief")
    project = vault.project
    if project is None:
        raise ValueError("bootstrap needs a current project")

    # 1) module notes — links always from the import graph; prose from the LLM
    #    (full mode) or from docstrings/AST (brief mode, free)
    for fmap in plan.modules:
        if brief:
            body = _render_brief_body(fmap)
        else:
            prompt = (f"{MODULE_PROMPT}\nMODULE: {fmap.dotted} ({fmap.language})\n"
                      f"SYMBOLS: {[s.name for s in fmap.symbols if s.exported]}\n"
                      f"SOURCE:\n{fmap.source[:settings.bootstrap_module_src_chars]}\n")
            try:
                data = _extract_json(provider.complete(prompt))
            except Exception as exc:
                log.append(f"skip module {fmap.dotted}: provider error: {exc}")
                continue
            if not data or "purpose" not in data:
                log.append(f"skip module {fmap.dotted}: unusable summary")
                continue
            body = _render_module_body(fmap.dotted, data)
        # Link to every project-internal dependency, selected or not: the
        # target note may exist already (stub) or arrive later — dangling
        # links are allowed by design and resolve as the vault fills in.
        deps = [_module_uri(vault, dep) for dep in plan.graph.get(fmap.dotted, [])]
        try:
            uri = vault.write_note(
                title=fmap.dotted, content=body,
                type="module", scope="shared",
                links={"depends_on": deps} if deps else None,
                source="distilled", protect=True,
            )
            log.append(f"module {uri}" + (" [brief]" if brief else ""))
        except PermissionError:
            log.append(f"skip module {fmap.dotted}: manual note exists")

    # 2) key function notes — one batched call (full mode only)
    if plan.functions and not brief:
        listing = "\n".join(
            f"- {f.dotted}.{name} (referenced in {refs} files):\n"
            f"{_function_snippet(f, name)}"
            for f, name, refs in plan.functions
        )
        try:
            data = _extract_json(provider.complete(f"{FUNCTIONS_PROMPT}\n{listing}\n")) or {}
        except Exception as exc:
            data = {}
            log.append(f"skip functions: provider error: {exc}")
        summaries = {str(e.get("name", "")): str(e.get("summary", ""))
                     for e in data.get("functions", []) if isinstance(e, dict)}
        for fmap, name, _refs in plan.functions:
            summary = summaries.get(name) or summaries.get(f"{fmap.dotted}.{name}")
            if not summary:
                continue
            try:
                uri = vault.write_note(
                    title=f"{fmap.dotted}.{name}",
                    content=f"# {fmap.dotted}.{name}\n\n{summary}\n",
                    type="function", scope="shared",
                    links={"part_of": [_module_uri(vault, fmap.dotted)]},
                    source="distilled", protect=True,
                )
                log.append(f"function {uri}")
            except PermissionError:
                log.append(f"skip function {fmap.dotted}.{name}: manual note exists")

    # 3) conventions/decisions — through the distiller ops pipeline (judged);
    #    skipped in brief mode (zero-LLM guarantee) AND in focused runs:
    #    conventions are project-wide, re-deriving them from one module's
    #    perspective over-generates trivia and duplicates.
    configs = "" if (brief or plan.focused) else _collect_configs(plan.repo_root)
    if configs:
        tree = "\n".join(str(m.path) for m in plan.modules)
        prompt = f"{CONVENTIONS_PROMPT}\nPROJECT FILES:\n{tree}\n\nCONFIGS:\n{configs}\n"
        try:
            ops_data = _extract_json(provider.complete(prompt)) or {}
            ops = ops_data.get("ops", [])
            if isinstance(ops, list) and ops:
                log += apply_ops(vault, ops, provider=provider,
                                 judge_distilled=judge_distilled)
        except Exception as exc:
            log.append(f"skip conventions: provider error: {exc}")

    # 4) draft root contracts for detected external calls (no LLM needed) —
    #    written as this project's CONSUMER section, so the provider project's
    #    section (and any hand-written content) is never touched.
    if registry is not None and plan.external_calls:
        from .contracts import upsert_contract_section

        member_roots = [name for name, root in registry.roots.items()
                        if project in root.members and name in vault.mounts]
        for root_name in member_roots:
            for dotted, url in plan.external_calls:
                title = re.sub(r"^https?://", "", url)
                try:
                    uri = upsert_contract_section(
                        vault, root_key=root_name, title=title,
                        project=project, role="consumer",
                        content=(f"Draft (bootstrap): `{project}` calls `{url}` "
                                 f"from `{dotted}`. Fill in schema/expectations."),
                    )
                    log.append(f"contract {uri} [consumer]")
                except Exception as exc:
                    log.append(f"skip contract {title}: {exc}")

    # 5) surface everything in _index.md and refresh the cache
    if project in vault.mounts:
        sync_index_auto_section(vault.mounts[project], project)
    vault.index.rebuild(vault.mounts)
    return log


def _function_snippet(fmap: FileMap, name: str, max_chars: int = 800) -> str:
    match = re.search(rf"(?:def|function|const)\s+{re.escape(name)}\b", fmap.source)
    if not match:
        return ""
    return fmap.source[match.start(): match.start() + max_chars]


def _collect_configs(repo_root: Path, max_chars: int = 6000) -> str:
    names = ["pyproject.toml", "package.json", "tsconfig.json", "ruff.toml",
             ".eslintrc.json", "setup.cfg", "Makefile"]
    chunks: list[str] = []
    used = 0
    for name in names:
        path = repo_root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")[: max_chars - used]
        chunks.append(f"--- {name} ---\n{text}")
        used += len(text)
        if used >= max_chars:
            break
    return "\n".join(chunks)
