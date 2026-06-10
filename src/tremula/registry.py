"""The genet registry and mount-set resolution.

Every project has its own vault (``ramet``); projects connect only through
explicit bridge vaults (``roots``) declared in a single registry file
(``~/.tremula/registry.yaml``). At session start the server identifies the
current project by cwd and computes its **mount set** — its own ramet plus every
root it is a member of. Everything outside the mount set is invisible: it never
appears in search, graph traversal, or injection.

The mount set is exactly the ``project -> vault root`` mapping that
:func:`tremula.memory_uri.resolve` consumes, so a ``memory://`` URI pointing
outside the set is unresolvable by construction.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .config import tremula_home

DEFAULT_REGISTRY_ENV = "TREMULA_REGISTRY"


def _expand(path: str | Path) -> Path:
    """Expand ``~`` and environment variables, then make absolute."""
    return Path(os.path.expandvars(str(path))).expanduser().resolve()


class ProjectEntry(BaseModel):
    """A single ramet: its vault directory and (optionally) its repo root."""

    path: Path  # the tremula-vault/ directory
    repo: Path | None = None  # repo root, used for cwd-based project detection

    @field_validator("path", "repo", mode="before")
    @classmethod
    def _expand_paths(cls, value):
        return _expand(value) if value is not None else None

    @property
    def detect_root(self) -> Path:
        """Directory used to match a cwd to this project (repo if set, else vault parent)."""
        return self.repo if self.repo is not None else self.path.parent


class RootEntry(BaseModel):
    """A bridge vault linking two or more ramets (shared contracts)."""

    members: list[str] = Field(min_length=1)
    path: Path

    @field_validator("path", mode="before")
    @classmethod
    def _expand_path(cls, value):
        return _expand(value)


class Registry(BaseModel):
    """The whole genet: all ramets plus the roots that connect them."""

    projects: dict[str, ProjectEntry] = Field(default_factory=dict)
    roots: dict[str, RootEntry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_root_members(self) -> Registry:
        for root_name, root in self.roots.items():
            for member in root.members:
                if member not in self.projects:
                    raise ValueError(
                        f"root {root_name!r} lists unknown project member "
                        f"{member!r} (known: {sorted(self.projects)})"
                    )
        # A registry key is a namespace; projects and roots must not collide.
        clash = set(self.projects) & set(self.roots)
        if clash:
            raise ValueError(f"keys used by both a project and a root: {sorted(clash)}")
        return self

    # ---- lookup -------------------------------------------------------------

    def find_project_by_cwd(self, cwd: str | Path | None = None) -> str | None:
        """Return the project key whose repo/vault contains ``cwd``.

        Picks the most specific match (longest containing path) so nested
        checkouts resolve to the innermost project.
        """
        cwd = _expand(cwd or Path.cwd())
        best: tuple[int, str] | None = None
        for name, project in self.projects.items():
            root = project.detect_root
            if cwd == root or root in cwd.parents:
                depth = len(root.parts)
                if best is None or depth > best[0]:
                    best = (depth, name)
        return best[1] if best else None

    def mount_set(self, project: str) -> dict[str, Path]:
        """Compute the ``key -> vault root`` map for ``project``.

        Includes the project's own ramet plus every root it is a member of.
        Both project keys and root keys are valid ``memory://`` namespaces.
        """
        if project not in self.projects:
            raise KeyError(f"unknown project {project!r} (known: {sorted(self.projects)})")
        mounts: dict[str, Path] = {project: self.projects[project].path}
        for root_name, root in self.roots.items():
            if project in root.members:
                mounts[root_name] = root.path
        return mounts


class RegistryError(RuntimeError):
    """Raised when the registry file cannot be located or parsed."""


def default_registry_path() -> Path:
    """The registry path: ``TREMULA_REGISTRY`` override, else under TREMULA_HOME.

    Anchoring to ``tremula_home()`` matters for isolation: a process started
    with ``TREMULA_HOME=/tmp/...`` (tests, sandboxes) must not silently read or
    write the user's real registry.
    """
    override = os.environ.get(DEFAULT_REGISTRY_ENV)
    return _expand(override) if override else tremula_home() / "registry.yaml"


def load_registry(path: str | Path | None = None, *, missing_ok: bool = True) -> Registry:
    """Load and validate the registry.

    With ``missing_ok`` (default), a missing file yields an empty registry so
    the server can start before any project is registered. A malformed or
    invalid file always raises :class:`RegistryError`.
    """
    path = _expand(path) if path is not None else default_registry_path()
    if not path.exists():
        if missing_ok:
            return Registry()
        raise RegistryError(f"registry not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise RegistryError(f"invalid YAML in {path}: {exc}") from exc
    try:
        return Registry.model_validate(raw)
    except ValueError as exc:
        raise RegistryError(f"invalid registry {path}: {exc}") from exc


class SessionContext(BaseModel):
    """The resolved view for one session: which project, and what it can see."""

    project: str | None
    mounts: dict[str, Path]  # key -> vault root; the project's mount set
    registry_path: Path

    @property
    def vault_root(self) -> Path | None:
        """The current project's own ramet directory, if a project was found."""
        return self.mounts.get(self.project) if self.project else None


def resolve_session(
    cwd: str | Path | None = None, path: str | Path | None = None
) -> SessionContext:
    """Identify the current project by cwd and compute its mount set.

    This is the single entry point the MCP server (Stage 3) calls at startup.
    If no project matches the cwd, ``project`` is ``None`` and ``mounts`` is
    empty — nothing is visible.
    """
    registry_path = _expand(path) if path is not None else default_registry_path()
    registry = load_registry(registry_path)
    project = registry.find_project_by_cwd(cwd)
    mounts = registry.mount_set(project) if project else {}
    return SessionContext(project=project, mounts=mounts, registry_path=registry_path)
