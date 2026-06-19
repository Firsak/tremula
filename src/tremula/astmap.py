"""AST map of a codebase via tree-sitter (python / typescript / tsx).

Bootstrap's deterministic layer: which source files exist, what symbols they
export, and which project files import which. The LLM never decides structure —
links between module notes come straight from this import graph.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from tree_sitter import Language, Parser

# Tremula's own always-junk default: dirs never worth mapping as code memory
# (dependency trees, build output, caches, VCS, Tremula's own state). Framework
# build dirs that vary per project (.next, .sst, .open-next, .turbo, …) belong
# in a repo-root ``.tremulaignore`` — Tremula owns this policy, not git.
SKIP_DIRS = {
    "node_modules", ".venv", "venv", ".git", "dist", "build", "out", "target",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "tremula-vault", ".tremula", ".claude", ".omc",
}
TEST_DIRS = {"test", "tests"}
EXTENSIONS = {".py": "python", ".ts": "typescript", ".tsx": "tsx"}
IGNORE_FILE = ".tremulaignore"


@dataclass
class Symbol:
    kind: str  # "function" | "class" | "const"
    name: str
    exported: bool
    line: int  # 1-based


@dataclass
class FileMap:
    path: Path  # relative to repo root
    language: str
    dotted: str  # project-unique module name, e.g. "tremula.vault"
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)  # raw import targets
    source: str = ""
    loc: int = 0
    docstring: str = ""  # module docstring (python), free zero-LLM summary


@cache
def _parser(language: str) -> Parser:
    if language == "python":
        import tree_sitter_python as tspy

        return Parser(Language(tspy.language()))
    import tree_sitter_typescript as tsts

    lang = tsts.language_tsx() if language == "tsx" else tsts.language_typescript()
    return Parser(Language(lang))


def _is_test_file(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("test_") or name.endswith("_test.py")
        or ".test." in name or ".spec." in name
        or "tests" in path.parts or "test" in path.parts
    )


def read_ignore_file(repo_root: str | Path) -> set[str]:
    """Per-project ignore: bare directory names from ``<repo>/.tremulaignore``.

    Tremula's own ignore artifact — committed with the project, travels with
    clones, no git involved. One directory name per line (not globs, matching
    the dir-pruning model); ``#`` comments and blank lines are skipped. Missing
    or unreadable file -> empty set.
    """
    path = Path(repo_root) / IGNORE_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return set()
    names: set[str] = set()
    for line in text.splitlines():
        name = line.split("#", 1)[0].strip().rstrip("/")
        if name:
            names.add(name)
    return names


def scan(repo_root: str | Path, *, extra_skip: set[str] | None = None) -> list[Path]:
    """Source files worth mapping, relative to the repo root (tests/junk skipped).

    Junk and test directories are PRUNED from the walk, not filtered after the
    fact — on the big repos that ``bootstrap --brief`` targets, descending into
    ``node_modules``/``.venv`` only to discard every entry dominates scan time.

    Tremula owns its ignore policy, composed from three Tremula-only sources (no
    git): the ``SKIP_DIRS`` always-junk default, the repo-root ``.tremulaignore``
    (per-project), and ``extra_skip`` (the per-machine ``bootstrap_skip_dirs``
    setting).
    """
    repo_root = Path(repo_root)
    skip = SKIP_DIRS | read_ignore_file(repo_root) | set(extra_skip or ())
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in skip and d not in TEST_DIRS
        )
        for filename in sorted(filenames):
            path = Path(dirpath, filename)
            if path.suffix not in EXTENSIONS:
                continue
            rel = path.relative_to(repo_root)
            if _is_test_file(rel):
                continue
            found.append(rel)
    return sorted(found)


def dotted_name(rel_path: Path) -> str:
    """Project-unique module name: ``src/tremula/vault.py`` -> ``tremula.vault``."""
    parts = list(rel_path.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else rel_path.stem


def map_file(repo_root: str | Path, rel_path: Path) -> FileMap:
    """Parse one source file into symbols + raw imports."""
    repo_root = Path(repo_root)
    language = EXTENSIONS[rel_path.suffix]
    source = (repo_root / rel_path).read_text(encoding="utf-8", errors="replace")
    fmap = FileMap(path=rel_path, language=language, dotted=dotted_name(rel_path),
                   source=source, loc=source.count("\n") + 1)
    tree = _parser(language).parse(source.encode("utf-8"))
    if language == "python":
        _walk_python(tree.root_node, fmap)
    else:
        _walk_ts(tree.root_node, fmap)
    return fmap


def resolve_symbol(repo_root: str | Path, rel_path: str | Path, symbol_name: str) -> bool:
    """Does ``symbol_name`` resolve in ``rel_path``'s current AST? (background-only).

    Used by the distiller's confirmation pass to verify a note's subject code is
    really present. Never raises: returns False if the file is missing, its
    language is unsupported (no tree-sitter grammar), or parsing fails. The
    symbol may be bare (``foo``) or dotted (``module.Class``) — only the trailing
    segment is matched against the file's declared symbols.
    """
    rel_path = Path(rel_path)
    if rel_path.suffix not in EXTENSIONS:
        return False
    if not (Path(repo_root) / rel_path).is_file():
        return False
    leaf = symbol_name.rsplit(".", 1)[-1]
    try:
        fmap = map_file(repo_root, rel_path)
    except Exception:
        return False
    return any(sym.name == leaf for sym in fmap.symbols)


def _walk_python(root, fmap: FileMap) -> None:
    # Module docstring: a leading expression-statement string.
    if not fmap.docstring and root.children:
        first = root.children[0]
        if first.type == "expression_statement" and first.children \
                and first.children[0].type == "string":
            raw = first.children[0].text.decode()
            fmap.docstring = raw.strip("\"' \n")
    for node in root.children:
        if node.type in ("function_definition", "class_definition"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            name = name_node.text.decode()
            fmap.symbols.append(Symbol(
                kind="function" if node.type == "function_definition" else "class",
                name=name,
                exported=not name.startswith("_"),
                line=node.start_point[0] + 1,
            ))
        elif node.type == "import_statement":
            for child in node.named_children:  # import a.b, c
                target = child.child_by_field_name("name") or child
                fmap.imports.append(target.text.decode())
        elif node.type == "import_from_statement":
            module = node.child_by_field_name("module_name")
            if module is not None:
                fmap.imports.append(module.text.decode())
        elif node.type == "decorated_definition":
            _walk_python(node, fmap)  # decorated top-level def/class


def _walk_ts(root, fmap: FileMap) -> None:
    for node in root.children:
        if node.type == "import_statement":
            src = node.child_by_field_name("source")
            if src is not None:
                fmap.imports.append(src.text.decode().strip("'\""))
        elif node.type == "export_statement":
            decl = node.child_by_field_name("declaration")
            if decl is not None:
                _ts_symbol(decl, fmap, exported=True)
        elif node.type in ("function_declaration", "class_declaration",
                           "lexical_declaration"):
            _ts_symbol(node, fmap, exported=False)


def _ts_symbol(decl, fmap: FileMap, exported: bool) -> None:
    if decl.type in ("function_declaration", "class_declaration"):
        name_node = decl.child_by_field_name("name")
        if name_node is not None:
            fmap.symbols.append(Symbol(
                kind="function" if decl.type == "function_declaration" else "class",
                name=name_node.text.decode(), exported=exported,
                line=decl.start_point[0] + 1,
            ))
    elif decl.type == "lexical_declaration":
        for declarator in decl.named_children:
            if declarator.type == "variable_declarator":
                name_node = declarator.child_by_field_name("name")
                if name_node is not None:
                    fmap.symbols.append(Symbol(
                        kind="const", name=name_node.text.decode(),
                        exported=exported, line=decl.start_point[0] + 1,
                    ))


def resolve_import(raw: str, importer: FileMap, by_dotted: dict[str, FileMap]) -> str | None:
    """Map a raw import target onto a project module's dotted name, if internal."""
    if raw.startswith("."):  # relative: python ".vault" / ts "./client", "../shared"
        base = importer.dotted.split(".")[:-1]
        if importer.language == "python":
            # Each leading dot beyond the first goes up one package level.
            ups = len(raw) - len(raw.lstrip(".")) - 1
            if ups:
                base = base[: len(base) - ups] if ups <= len(base) else []
            cleaned = raw.lstrip(".")
        else:
            # TS/TSX: "./x" stays in the dir; each "../" goes up one directory.
            rest = raw
            while True:
                if rest.startswith("./"):
                    rest = rest[2:]
                elif rest.startswith("../"):
                    base = base[:-1]
                    rest = rest[3:]
                else:
                    break
            cleaned = rest
        tail = [p for p in cleaned.replace("/", ".").split(".") if p] if cleaned else []
        candidate = ".".join([*base, *tail])
        return candidate if candidate and candidate in by_dotted else None
    dotted = raw.replace("/", ".")
    return dotted if dotted in by_dotted else None


def import_graph(files: list[FileMap]) -> dict[str, list[str]]:
    """``dotted -> [imported project dotteds]`` from raw imports (deterministic)."""
    by_dotted = {f.dotted: f for f in files}
    graph: dict[str, list[str]] = {}
    for fmap in files:
        targets: list[str] = []
        for raw in fmap.imports:
            resolved = resolve_import(raw, fmap, by_dotted)
            if resolved and resolved != fmap.dotted and resolved not in targets:
                targets.append(resolved)
        graph[fmap.dotted] = targets
    return graph
