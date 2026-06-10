"""The ``tremula`` command-line entry point.

Stage 1 ships the skeleton plus a ``vault`` inspector. The ambient ``hook``
subcommand (NDJSON capture) and the distiller land in Stage 3.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .note import load_note_in_vault


def _find_vault(start: Path) -> Path | None:
    for parent in [start, *start.parents]:
        candidate = parent / "tremula-vault"
        if candidate.is_dir():
            return candidate
    return None


def _cmd_vault(args: argparse.Namespace) -> int:
    vault = _find_vault(Path.cwd())
    if vault is None:
        print("no tremula-vault/ found from cwd upward", file=sys.stderr)
        return 1
    project = args.project or vault.parent.name
    notes = sorted(vault.rglob("*.md"))
    print(f"vault: {vault}  ({len(notes)} notes, project={project})")
    for path in notes:
        note = load_note_in_vault(path, vault, project)
        print(f"  {note.uri}  [{note.frontmatter.type.value}]  {note.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tremula", description="Tremula code-memory CLI")
    parser.add_argument("--version", action="version", version=f"tremula {__version__}")
    sub = parser.add_subparsers(dest="command")

    vault = sub.add_parser("vault", help="list notes in the current project's vault")
    vault.add_argument("--project", help="project key (defaults to repo dir name)")
    vault.set_defaults(func=_cmd_vault)

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
