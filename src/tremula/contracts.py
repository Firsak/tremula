"""Contract notes in root vaults: one note per contract, one section per side.

A root (bridge vault) holds the contracts two projects share — endpoints,
common types, event schemas. Each member project maintains ONLY its own
section of the note ("## Provider (api)" / "## Consumer (webapp)"), written by
its distiller or bootstrap. Sections from different sides coexist in one file,
so contract drift is literally visible: when the provider's section and the
consumer's section disagree, the note shows both claims side by side.

The section merge is surgical by construction — a writer can never touch
another side's section, no matter what its LLM produced.
"""

from __future__ import annotations

import re

import frontmatter

from .memory_uri import MemoryURIError, resolve
from .vault import VaultService

ROLES = ("provider", "consumer")

_SECTION_RE = re.compile(
    r"^## (?:Provider|Consumer) \([A-Za-z0-9_-]+\)$", re.MULTILINE
)


def section_heading(role: str, project: str) -> str:
    return f"## {role.capitalize()} ({project})"


def _split_sections(body: str) -> tuple[str, dict[str, str]]:
    """Split a contract body into (preamble, {heading: section_text})."""
    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        return body, {}
    preamble = body[: matches[0].start()]
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[match.group(0)] = body[match.end(): end].strip("\n")
    return preamble, sections


def upsert_contract_section(
    vault: VaultService,
    root_key: str,
    title: str,
    project: str,
    role: str,
    content: str,
) -> str:
    """Create/update ONLY this project's section of a contract note in a root.

    Returns the note's ``memory://`` URI. Raises ``MemoryURIError`` when the
    root is not in the mount set (a project cannot write into a root it is not
    a member of) and ``ValueError`` on a bad role.
    """
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    if root_key not in vault.mounts:
        raise MemoryURIError(
            f"root {root_key!r} is not in the mount set {sorted(vault.mounts)}"
        )

    uri = vault.target_uri(title, "contract", project=root_key)
    path = resolve(uri, vault.mounts)

    if path.exists():
        post = frontmatter.load(path)
        preamble, sections = _split_sections(post.content)
        metadata = dict(post.metadata)
    else:
        preamble = f"# {title}\n\nShared contract — each side maintains its own section.\n"
        sections = {}
        metadata = {"type": "contract", "scope": "shared", "source": "distilled"}

    sections[section_heading(role, project)] = content.strip()

    body = preamble.rstrip("\n") + "\n"
    for heading in sorted(sections):  # stable order: Consumer (...), Provider (...)
        body += f"\n{heading}\n\n{sections[heading]}\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body, **metadata)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    # Pull-based consistency picks the change up; refresh eagerly for callers
    # that query right away.
    vault.index.refresh(vault.mounts)
    return uri
