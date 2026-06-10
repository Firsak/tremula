"""The ``tremula`` command-line entry point.

Stage 1 shipped the ``vault`` inspector. Stage 2 adds ``registry`` (show the
genet and the current session's mount set) and ``registry init`` (register the
current project). The ambient ``hook`` subcommand and the distiller land in
Stage 3.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import __version__
from .note import load_note_in_vault
from .registry import (
    Registry,
    RegistryError,
    default_registry_path,
    load_registry,
    resolve_session,
)


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
    print(f"vault: {vault}  ({len(notes)} notes, project={project}, via {source})")
    for path in notes:
        note = load_note_in_vault(path, vault, project)
        print(f"  {note.uri}  [{note.frontmatter.type.value}]  {note.title}")
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
    """Register the current project in the registry (non-destructive)."""
    reg_path = default_registry_path()
    repo = Path.cwd().resolve()
    vault = repo / "tremula-vault"
    if not vault.is_dir():
        print(f"no tremula-vault/ in {repo}", file=sys.stderr)
        return 1
    name = args.name or repo.name

    data = {}
    if reg_path.exists():
        data = yaml.safe_load(reg_path.read_text()) or {}
    projects = data.setdefault("projects", {})
    if name in projects and not args.force:
        print(f"project {name!r} already registered (use --force to overwrite)",
              file=sys.stderr)
        return 1
    projects[name] = {"path": str(vault), "repo": str(repo)}

    # Validate the result before writing.
    try:
        Registry.model_validate(data)
    except ValueError as exc:
        print(f"refusing to write invalid registry: {exc}", file=sys.stderr)
        return 1

    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(yaml.safe_dump(data, sort_keys=True))
    print(f"registered {name!r} -> {vault}\nregistry: {reg_path}")
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
    reg_init.set_defaults(func=_cmd_registry_init)
    registry.set_defaults(func=_cmd_registry)

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
