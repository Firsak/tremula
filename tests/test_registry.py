"""Stage 2 acceptance: registry validation + mount-set resolution by cwd."""

from pathlib import Path

import pytest
import yaml

from tremula.memory_uri import MemoryURIError, resolve
from tremula.registry import (
    Registry,
    RegistryError,
    load_registry,
    resolve_session,
)


def _build_genet(tmp_path: Path) -> Path:
    """Create webapp/api/custovis repos + a webapp-api root; return registry path."""
    for name in ("webapp", "api", "custovis"):
        (tmp_path / name / "tremula-vault").mkdir(parents=True)
    (tmp_path / "roots" / "webapp-api").mkdir(parents=True)

    registry = {
        "projects": {
            "webapp": {
                "path": str(tmp_path / "webapp" / "tremula-vault"),
                "repo": str(tmp_path / "webapp"),
            },
            "api": {
                "path": str(tmp_path / "api" / "tremula-vault"),
                "repo": str(tmp_path / "api"),
            },
            "custovis": {
                "path": str(tmp_path / "custovis" / "tremula-vault"),
                "repo": str(tmp_path / "custovis"),
            },
        },
        "roots": {
            "webapp-api": {
                "members": ["webapp", "api"],
                "path": str(tmp_path / "roots" / "webapp-api"),
            }
        },
    }
    reg_path = tmp_path / "registry.yaml"
    reg_path.write_text(yaml.safe_dump(registry))
    return reg_path


def test_load_and_validate(tmp_path):
    reg = load_registry(_build_genet(tmp_path))
    assert set(reg.projects) == {"webapp", "api", "custovis"}
    assert reg.roots["webapp-api"].members == ["webapp", "api"]


def test_missing_file_ok_by_default(tmp_path):
    reg = load_registry(tmp_path / "nope.yaml")
    assert reg.projects == {}


def test_missing_file_strict_raises(tmp_path):
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "nope.yaml", missing_ok=False)


def test_unknown_root_member_rejected():
    with pytest.raises(ValueError, match="unknown project member"):
        Registry.model_validate(
            {
                "projects": {"webapp": {"path": "/tmp/webapp/tremula-vault"}},
                "roots": {"r": {"members": ["webapp", "ghost"], "path": "/tmp/r"}},
            }
        )


def test_project_root_key_collision_rejected():
    with pytest.raises(ValueError, match="both a project and a root"):
        Registry.model_validate(
            {
                "projects": {"shared": {"path": "/tmp/a/tremula-vault"}},
                "roots": {"shared": {"members": ["shared"], "path": "/tmp/r"}},
            }
        )


def test_find_project_by_cwd_longest_match(tmp_path):
    reg = load_registry(_build_genet(tmp_path))
    # cwd deep inside the webapp repo resolves to webapp.
    deep = tmp_path / "webapp" / "src" / "components"
    deep.mkdir(parents=True)
    assert reg.find_project_by_cwd(deep) == "webapp"
    assert reg.find_project_by_cwd(tmp_path) is None  # outside every repo


def test_mount_set_includes_member_roots_only(tmp_path):
    reg = load_registry(_build_genet(tmp_path))
    webapp_mounts = reg.mount_set("webapp")
    assert set(webapp_mounts) == {"webapp", "webapp-api"}  # own ramet + member root
    custovis_mounts = reg.mount_set("custovis")
    assert set(custovis_mounts) == {"custovis"}  # not a member of any root


def test_resolve_session_by_cwd(tmp_path):
    reg_path = _build_genet(tmp_path)
    ctx = resolve_session(cwd=tmp_path / "api", path=reg_path)
    assert ctx.project == "api"
    assert set(ctx.mounts) == {"api", "webapp-api"}
    assert ctx.vault_root == (tmp_path / "api" / "tremula-vault").resolve()


def test_mount_set_drives_memory_resolve(tmp_path):
    """The mount set is exactly what memory_uri.resolve consumes."""
    reg = load_registry(_build_genet(tmp_path))
    mounts = reg.mount_set("webapp")
    # in-set: own ramet and the shared root both resolve
    assert resolve("memory://webapp/modules/auth", mounts).name == "auth.md"
    assert resolve("memory://webapp-api/post-inspections", mounts).parent.name == "webapp-api"
    # out-of-set: api is invisible from webapp's session
    with pytest.raises(MemoryURIError, match="not in the mount set"):
        resolve("memory://api/modules/auth", mounts)


def test_tilde_path_expands():
    reg = Registry.model_validate(
        {"projects": {"home": {"path": "~/code/home/tremula-vault"}}}
    )
    assert not str(reg.projects["home"].path).startswith("~")
    assert reg.projects["home"].path.is_absolute()
