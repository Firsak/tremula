"""AST map of a codebase via tree-sitter (python / typescript / tsx).

Bootstrap's deterministic layer: which source files exist, what symbols they
export, and which project files import which. The LLM never decides structure —
links between module notes come straight from this import graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from tree_sitter import Language, Parser

SKIP_DIRS = {
    "node_modules", ".venv", "venv", ".git", "dist", "build", "out", "target",
    "__pycache__", ".pytest_cache", ".ruff_cache", "tremula-vault", ".tremula",
    ".claude", ".omc",
}
EXTENSIONS = {".py": "python", ".ts": "typescript", ".tsx": "tsx"}


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


def scan(repo_root: str | Path) -> list[Path]:
    """Source files worth mapping, relative to the repo root (tests/junk skipped)."""
    repo_root = Path(repo_root)
    found: list[Path] = []
    for path in sorted(repo_root.rglob("*")):
        if path.suffix not in EXTENSIONS or not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        if any(part in SKIP_DIRS for part in rel.parts) or _is_test_file(rel):
            continue
        found.append(rel)
    return found


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
    if raw.startswith("."):  # relative: python ".vault" / ts "./client"
        base = importer.dotted.split(".")[:-1]
        cleaned = raw.lstrip("./")
        # python relative depth: each extra leading dot beyond the first goes up
        if importer.language == "python":
            ups = len(raw) - len(raw.lstrip(".")) - 1
            base = base[: len(base) - ups] if ups else base
            cleaned = raw.lstrip(".")
        candidate = ".".join([*base, *cleaned.replace("/", ".").split(".")]) if cleaned \
            else ".".join(base)
        return candidate if candidate in by_dotted else None
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
