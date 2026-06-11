---
depends_on:
- memory://tremula/modules/tremula-config
scope: shared
source: distilled
type: module
---

# tremula.registry

Manages the federated vault system: stores project-to-vault mappings and bridge vaults that connect them. At session start, computes the mount set for each project—the vaults it can see (its own ramet plus any roots it belongs to). Everything outside the mount set is invisible to search and URI resolution.

## Public API
- `load_registry(path, missing_ok=True)` — Load and validate registry from YAML; missing_ok allows empty registry at startup
- `Registry` — Root config object holding all projects and bridge vaults with validation
- `ProjectEntry` — Single project: vault path and optional repo root for cwd-based detection
- `RootEntry` — Bridge vault linking two or more projects by name
- `default_registry_path()` — Get registry path with TREMULA_REGISTRY env override; isolated by TREMULA_HOME
- `Registry.mount_set(project)` — Compute key→vault-root map for project (its ramet + member roots)
- `Registry.find_project_by_cwd(cwd)` — Resolve cwd to project key by longest-matching repo or vault parent
- `RegistryError` — Exception raised on registry load/parse failure
