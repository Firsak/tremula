---
confirmation_count: 0
scope: backend
source: distilled
status: ratified
subject_paths:
- src/tremula/config.py
subject_symbols:
- tremula.config.Settings
type: module
---

# tremula.config

Central directory paths and distiller provider configuration. Manages all rebuildable state under $TREMULA_HOME (sessions, SQLite index, config), and abstracts the distiller's LLM backend so switching providers is one setting, not a code change.

## Public API
- `tremula_home()` — Root directory for all rebuildable state; honors $TREMULA_HOME environment variable
- `sessions_dir(project: str)` — Path to session capture logs for a project
- `index_path(project: str)` — Path to the SQLite FTS5 index for a project
- `config_path()` — Path to config.yaml in the home directory
- `hooks_disabled()` — Check if ambient hooks are disabled via environment variable
- `ProviderConfig` — Pydantic model for distiller LLM config (kind, model, base_url, auth_env)
- `Settings` — All configuration tunables with sane defaults (provider, note sizes, distill intervals, attachment logic, and note-lifecycle scoping: `lifecycle_enabled` master toggle, `confirmation_threshold` default 3 to ratify a provisional note, `confirmation_batch_size` default 30 bounding the background confirmation pass)
- `load_settings()` — Load settings from config.yaml if present, else return defaults
