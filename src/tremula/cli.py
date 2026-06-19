"""The ``tremula`` command-line entry point.

Commands: ``vault`` (inspect notes) · ``registry`` / ``registry init`` /
``root add`` (genet topology and mount sets) · ``index rebuild`` · ``serve``
(MCP server over stdio) · ``hook <event>`` (ambient capture/injection
dispatch) · ``distill`` (detached background worker) · ``bootstrap`` (generate
the vault from source code) · ``revise`` (split/merge/archive janitor) ·
``verify`` (note-lifecycle cleanup: prune/ratify/lower provisional notes).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from . import __version__
from .config import index_path, load_settings, tremula_home
from .distiller import provider_from_config, run_distill
from .hooks import run_hook
from .index import Index, _decode_paths
from .note import load_note_in_vault
from .registry import (
    PROJECT_OVERRIDE_ENV,
    Registry,
    RegistryError,
    default_registry_path,
    load_registry,
    resolve_session,
)
from .server import serve
from .vault import VaultService


def _find_vault_upward(start: Path) -> Path | None:
    for parent in [start, *start.parents]:
        candidate = parent / "tremula-vault"
        if candidate.is_dir():
            return candidate
    return None


def _cmd_vault(args: argparse.Namespace) -> int:
    """List notes in the current project's vault, preferring registry resolution."""
    ctx = resolve_session()
    if ctx.vault_root is not None:
        vault, project = ctx.vault_root, ctx.project
        source = "registry"
    else:
        vault = _find_vault_upward(Path.cwd())
        if vault is None:
            print("no project for cwd in registry and no tremula-vault/ found upward",
                  file=sys.stderr)
            return 1
        project = args.project or vault.parent.name
        source = "cwd-fallback"

    notes = sorted(vault.rglob("*.md"))
    threshold = load_settings().confirmation_threshold
    print(f"vault: {vault}  ({len(notes)} notes, project={project}, via {source})")
    for path in notes:
        note = load_note_in_vault(path, vault, project)
        fm = note.frontmatter
        # Counter shown only while provisional; ratified notes (incl. grandfathered
        # ones at count 0) display a bare [ratified].
        tag = ("[ratified]" if fm.status.value == "ratified"
               else f"[provisional {fm.confirmation_count}/{threshold}]")
        print(f"  {note.uri}  [{fm.type.value}] {tag}  {note.title}")
    return 0


def _cmd_registry(args: argparse.Namespace) -> int:
    """Show the registry, the detected current project, and its mount set."""
    try:
        ctx = resolve_session()
        registry = load_registry(ctx.registry_path)
    except RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"registry: {ctx.registry_path}"
          f"{'' if ctx.registry_path.exists() else '  (does not exist yet)'}")
    print(f"projects ({len(registry.projects)}):")
    for name, project in registry.projects.items():
        print(f"  {name}: {project.path}")
    print(f"roots ({len(registry.roots)}):")
    for name, root in registry.roots.items():
        print(f"  {name}: [{', '.join(root.members)}] -> {root.path}")

    print(f"\ncurrent project (by cwd): {ctx.project or '(none)'}")
    if ctx.mounts:
        print("mount set:")
        for key, path in ctx.mounts.items():
            print(f"  memory://{key}/  -> {path}")
    return 0


def _cmd_registry_init(args: argparse.Namespace) -> int:
    """Register the current project, creating ``tremula-vault/`` if absent.

    ``init`` is the first command a new project runs, so it creates the vault
    directory and its ``_index.md`` (deadlock-breaker: ``bootstrap`` needs
    registration, and a registered project needs a vault). It also self-heals an
    existing vault that is missing ``_index.md`` — e.g. one made by hand or by a
    pre-0.1.3 init. ``--no-create`` only records an existing vault and fails if
    none is present.
    """
    reg_path = default_registry_path()
    repo = Path.cwd().resolve()
    vault = repo / "tremula-vault"
    created = False
    if not vault.is_dir():
        if args.no_create:
            print(f"no tremula-vault/ in {repo} (omit --no-create to create it)",
                  file=sys.stderr)
            return 1
        vault.mkdir(parents=True)
        created = True
    # Project key: explicit --name wins, then $TREMULA_PROJECT (so .mcp.json can
    # own the name), else the repo directory basename.
    name = args.name or os.environ.get(PROJECT_OVERRIDE_ENV) or repo.name

    data = {}
    if reg_path.exists():
        data = yaml.safe_load(reg_path.read_text()) or {}
    projects = data.setdefault("projects", {})
    if name in projects and not args.force:
        print(f"project {name!r} already registered (use --force to overwrite)",
              file=sys.stderr)
        return 1
    # Rename: if this repo is already registered under a different key, --force
    # replaces that entry so the cwd doesn't resolve to two competing projects.
    repo_str, vault_str = str(repo), str(vault)
    dupes = [k for k, p in projects.items()
             if k != name and isinstance(p, dict)
             and (p.get("repo") == repo_str or p.get("path") == vault_str)]
    if dupes and not args.force:
        print(f"this repo is already registered as {dupes[0]!r}; "
              f"use --force to rename it to {name!r}", file=sys.stderr)
        return 1
    for stale in dupes:
        del projects[stale]
    projects[name] = {"path": str(vault), "repo": str(repo)}

    # Validate the result before writing.
    try:
        Registry.model_validate(data)
    except ValueError as exc:
        print(f"refusing to write invalid registry: {exc}", file=sys.stderr)
        return 1

    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(yaml.safe_dump(data, sort_keys=True))
    # Ensure _index.md exists — self-heals a hand-made or pre-0.1.3 vault, and
    # keeps index_md as the single source of the scaffold (no duplicate here).
    from .index_md import sync_index_auto_section
    index_added = not (vault / "_index.md").exists()
    sync_index_auto_section(vault, name)
    if created:
        print(f"created vault {vault}")
    elif index_added:
        print(f"created {vault / '_index.md'}")
    print(f"registered {name!r} -> {vault}\nregistry: {reg_path}")
    return 0


def _cmd_hook(args: argparse.Namespace) -> int:
    # Hooks must never fail a session; run_hook swallows errors and returns 0.
    return run_hook(args.event)


def _cmd_serve(args: argparse.Namespace) -> int:
    return serve()


def _cmd_index(args: argparse.Namespace) -> int:
    ctx = resolve_session()
    if not ctx.project:
        print("no registered project for cwd; run `tremula registry init`", file=sys.stderr)
        return 1
    index = Index(index_path(ctx.project))
    n = index.rebuild(ctx.mounts)
    print(f"indexed {n} notes for project={ctx.project} -> {index.db_path}")
    return 0


def _cmd_distill(args: argparse.Namespace) -> int:
    """Distill a captured session into notes (invoked detached by the Stop hook).

    Incremental: consumes only events appended since the last run (byte-offset
    sidecar), under a per-session lock so runs never overlap.
    """
    try:
        registry = load_registry()
        if args.project not in registry.projects:
            print(f"unknown project {args.project!r}", file=sys.stderr)
            return 1
        settings = load_settings()
        mounts = registry.mount_set(args.project)
        index = Index(index_path(args.project))
        index.rebuild(mounts)
        vault = VaultService(mounts, index, project=args.project)
        provider = provider_from_config(settings.provider)
        # The code repo (not the vault) — enables working-tree confirmation.
        repo_root = registry.projects[args.project].repo
        applied = run_distill(
            args.session_file, vault, provider,
            trigger=args.trigger, prompt_budget=settings.distill_prompt_budget,
            judge_distilled=settings.judge_distilled_updates,
            repo_root=repo_root,
        )
    except Exception as exc:  # detached process: log to stderr, never crash a session
        print(f"distill error: {exc}", file=sys.stderr)
        return 1
    for line in applied:
        print(line)
    return 0


def _cmd_revise(args: argparse.Namespace) -> int:
    """Run a revision pass (split oversized / merge dupes / archive stale)."""
    from .revise import release_project_revise_lock, revise, try_project_revise_lock

    ctx = resolve_session()
    if not ctx.project:
        print("no registered project for cwd; run `tremula registry init`", file=sys.stderr)
        return 1
    if not args.dry_run and not try_project_revise_lock(ctx.project):
        print("a revision pass is already running for this project; try again later")
        return 0
    try:
        settings = load_settings()
        index = Index(index_path(ctx.project))
        index.rebuild(ctx.mounts)
        vault = VaultService(ctx.mounts, index, project=ctx.project)
        provider = None
        if not args.dry_run:
            provider = provider_from_config(settings.provider)
        for line in revise(vault, provider, settings, dry_run=args.dry_run):
            print(line)
    finally:
        if not args.dry_run:
            release_project_revise_lock(ctx.project)
    return 0


def _set_note_status(vault: VaultService, uri: str, status: str, count: int) -> int:
    """Rewrite a note's lifecycle fields (content preserved). The manual escape
    hatch behind ``verify --ratify`` / ``--lower``."""
    try:
        note = vault.read_note(uri, track=False)
    except Exception as exc:
        print(f"cannot read {uri}: {exc}", file=sys.stderr)
        return 1
    vault.write_note(
        title=note["title"], content=note["body"], type=note["type"],
        scope=note["scope"], links=note["links"], source=note["source"], protect=False,
        status=status, confirmation_count=count,
        subject_paths=note["subject_paths"], subject_symbols=note["subject_symbols"],
    )
    print(f"{uri} -> {status} ({count})")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    """Verification / cleaning pass — the ONLY path that prunes notes or lowers
    trust. Run it when you declare the current code state canonical.

    Default (``--dry-run``-style) lists provisional notes whose subject code is
    absent from the working tree; ``--prune`` archives them to attic/;
    ``--ratify``/``--lower`` set a single note's status by hand.
    """
    ctx = resolve_session()
    if not ctx.project or ctx.vault_root is None:
        print("no registered project for cwd; run `tremula registry init`", file=sys.stderr)
        return 1
    settings = load_settings()
    index = Index(index_path(ctx.project))
    index.rebuild(ctx.mounts)
    vault = VaultService(ctx.mounts, index, project=ctx.project)

    if args.ratify:
        return _set_note_status(vault, args.ratify, "ratified", settings.confirmation_threshold)
    if args.lower:
        return _set_note_status(vault, args.lower, "provisional", 0)

    registry = load_registry()
    repo_root = registry.projects[ctx.project].repo or Path.cwd()
    candidates: list[tuple[str, int, list[str]]] = []
    for row in index.provisional_notes(limit=100_000):
        paths = _decode_paths(row["subject_paths"])
        if not paths:
            continue  # no subject binding to judge against
        if any((Path(repo_root) / p).is_file() for p in paths):
            continue  # subject code present -> keep
        candidates.append((row["uri"], row["confirmation_count"], paths))

    if not candidates:
        print("no provisional notes with absent subject code.")
        return 0
    for uri, count, paths in candidates:
        print(f"[provisional {count}/{settings.confirmation_threshold}] {uri} "
              f"-- subject_paths absent: {', '.join(paths)}")
    if args.prune:
        from .revise import archive_note
        for uri, _count, _paths in candidates:
            archive_note(vault, uri, reason="verify: subject code absent (user-declared canonical)")
        print(f"\npruned {len(candidates)} note(s) to attic/")
    else:
        print(f"\n{len(candidates)} candidate(s). Re-run with --prune to archive them, "
              "or --ratify <uri> to keep one.")
    return 0


def _cmd_root_add(args: argparse.Namespace) -> int:
    """Declare a bridge vault (root) connecting member projects."""
    reg_path = default_registry_path()
    data = {}
    if reg_path.exists():
        data = yaml.safe_load(reg_path.read_text()) or {}
    members = [m.strip() for m in args.members.split(",") if m.strip()]
    if len(members) < 2:
        print("a root needs at least two members (--members a,b)", file=sys.stderr)
        return 1
    roots = data.setdefault("roots", {})
    if args.name in roots and not args.force:
        print(f"root {args.name!r} already declared (use --force to overwrite)",
              file=sys.stderr)
        return 1
    path = Path(args.path).expanduser().resolve() if args.path \
        else tremula_home() / "roots" / args.name
    roots[args.name] = {"members": members, "path": str(path)}
    try:
        Registry.model_validate(data)  # rejects unknown members / key collisions
    except ValueError as exc:
        print(f"refusing to write invalid registry: {exc}", file=sys.stderr)
        return 1
    path.mkdir(parents=True, exist_ok=True)
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(yaml.safe_dump(data, sort_keys=True))
    print(f"declared root {args.name!r} [{', '.join(members)}] -> {path}")
    return 0


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    """Generate the initial vault from the current project's source code."""
    from .bootstrap import plan_bootstrap, run_bootstrap

    ctx = resolve_session()
    if not ctx.project or ctx.vault_root is None:
        print("no registered project for cwd; run `tremula registry init`", file=sys.stderr)
        return 1
    settings = load_settings()
    repo_root = Path.cwd().resolve()
    plan = plan_bootstrap(
        repo_root,
        max_modules=args.max_modules or settings.bootstrap_max_modules,
        max_functions=args.functions or settings.bootstrap_functions,
        only=args.targets or None,
        extra_skip=set(settings.bootstrap_skip_dirs),
    )
    if args.targets and not plan.modules:
        print(f"no modules match {args.targets!r}", file=sys.stderr)
        return 1
    provider = None
    if not args.dry_run and not args.brief:
        provider = provider_from_config(settings.provider)
    index = Index(index_path(ctx.project))
    index.rebuild(ctx.mounts)
    vault = VaultService(ctx.mounts, index, project=ctx.project)
    registry = load_registry()
    log = run_bootstrap(
        vault, provider, plan, settings, registry=registry,
        dry_run=args.dry_run, judge_distilled=settings.judge_distilled_updates,
        brief=args.brief,
    )
    for line in log:
        print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tremula", description="Tremula code-memory CLI")
    parser.add_argument("--version", action="version", version=f"tremula {__version__}")
    sub = parser.add_subparsers(dest="command")

    vault = sub.add_parser("vault", help="list notes in the current project's vault")
    vault.add_argument("--project", help="project key when falling back (no registry)")
    vault.set_defaults(func=_cmd_vault)

    registry = sub.add_parser("registry", help="show the registry and current mount set")
    reg_sub = registry.add_subparsers(dest="registry_command")
    reg_init = reg_sub.add_parser("init", help="register the current project")
    reg_init.add_argument("--name", help="project key (defaults to repo dir name)")
    reg_init.add_argument("--force", action="store_true", help="overwrite existing entry")
    reg_init.add_argument("--no-create", action="store_true",
                          help="only record an existing tremula-vault/; do not create one")
    reg_init.set_defaults(func=_cmd_registry_init)
    registry.set_defaults(func=_cmd_registry)

    hook = sub.add_parser("hook", help="ambient hook entry (reads a payload on stdin)")
    hook.add_argument("event", help="hook event name, e.g. SessionStart, PostToolUse, Stop")
    hook.set_defaults(func=_cmd_hook)

    serve_p = sub.add_parser("serve", help="run the MCP server over stdio")
    serve_p.set_defaults(func=_cmd_serve)

    index_p = sub.add_parser("index", help="index operations")
    index_sub = index_p.add_subparsers(dest="index_command")
    index_rebuild = index_sub.add_parser("rebuild", help="rebuild the index from markdown")
    index_rebuild.set_defaults(func=_cmd_index)
    index_p.set_defaults(func=_cmd_index)

    revise_p = sub.add_parser("revise",
                              help="self-organize the vault: split oversized, merge "
                                   "duplicates, archive stale (distilled notes only)")
    revise_p.add_argument("--dry-run", action="store_true",
                          help="list candidates with reasons; change nothing, no LLM")
    revise_p.set_defaults(func=_cmd_revise)

    verify_p = sub.add_parser(
        "verify",
        help="lifecycle cleaning: list/prune provisional notes whose subject code "
             "is absent, or hand-set a note's trust (the only path that lowers trust)")
    verify_p.add_argument("--prune", action="store_true",
                          help="archive the listed notes to attic/ (recoverable, not deleted)")
    verify_p.add_argument("--ratify", metavar="URI",
                          help="mark one note ratified (always injection-eligible)")
    verify_p.add_argument("--lower", metavar="URI",
                          help="reset one note to provisional, confirmation_count=0")
    verify_p.set_defaults(func=_cmd_verify)

    root_p = sub.add_parser("root", help="bridge-vault (root) operations")
    root_sub = root_p.add_subparsers(dest="root_command", required=True)
    root_add = root_sub.add_parser("add", help="declare a root connecting member projects")
    root_add.add_argument("name", help="root key, e.g. webapp-api")
    root_add.add_argument("--members", required=True,
                          help="comma-separated registered project keys")
    root_add.add_argument("--path", help="root vault dir (default: ~/.tremula/roots/<name>)")
    root_add.add_argument("--force", action="store_true", help="overwrite existing root")
    root_add.set_defaults(func=_cmd_root_add)

    boot = sub.add_parser("bootstrap", help="generate the initial vault from source code")
    boot.add_argument("targets", nargs="*",
                      help="focus on specific files/dirs/modules (e.g. src/core/ or "
                           "pkg.module); empty = whole project. Typical big-repo flow: "
                           "`bootstrap --brief` once, then `bootstrap <target>` to "
                           "deep-enrich where it matters")
    boot.add_argument("--dry-run", action="store_true",
                      help="print the plan (modules, functions, call count); no LLM, no writes")
    boot.add_argument("--brief", action="store_true",
                      help="zero-LLM stub bootstrap (docstrings + AST symbols); the ambient "
                           "distiller enriches notes as you work — recommended for big repos")
    boot.add_argument("--max-modules", type=int, default=None,
                      help="cap on module notes (default from settings: 40)")
    boot.add_argument("--functions", type=int, default=None,
                      help="cap on key-function notes (default from settings: 10)")
    boot.set_defaults(func=_cmd_bootstrap)

    distill_p = sub.add_parser("distill", help="distill a captured session into notes")
    distill_p.add_argument("session_file", help="path to the session NDJSON file")
    distill_p.add_argument("--project", required=True, help="project key to distill into")
    distill_p.add_argument("--trigger", default="Stop",
                           help="hook event that triggered this run (Stop/PreCompact/SessionEnd)")
    distill_p.set_defaults(func=_cmd_distill)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
