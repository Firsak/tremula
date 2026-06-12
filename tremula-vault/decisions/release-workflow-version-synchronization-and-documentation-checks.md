---
depends_on:
- memory://tremula/decisions/decision-trusted-publishing-via-oidc-for-pypi-releases
- memory://tremula/decisions/decision-public-documentation-uses-feature-names-not-internal-stages
scope: backend
source: distilled
type: decision
---

# Release workflow: version synchronization and documentation checks

Tremula's release process requires coordination between source code and package metadata.

**Version synchronization:** The package version must match exactly across `pyproject.toml` (`[project] version`) and `src/tremula/__init__.py` (`__version__`). Mismatches cause either build failures or incorrect version reporting by the CLI. Verify both are in sync before running `uv build` and uploading to PyPI.

**Documentation accuracy at release time:** README.md and other user-facing docs are published to PyPI when uploading and cannot be edited after the fact — only a new version can fix them. Stale docs in a release (e.g., wrong status, incomplete feature lists, incorrect stage descriptions) immediately reach all users. Review user-facing docs for accuracy against actual project state before building release artifacts. A common failure: README describing outdated status ("Stage 1 complete, Stages 2–7 deferred") when later stages are already built and committed.

**Yanking previous releases:** If a release reaches PyPI and is later discovered to have errors (stale docs, broken deps, etc.), yank it via the PyPI web UI (project page → Manage → release version → Options → Yank). Yanking removes it from default version resolution but keeps it installable if explicitly pinned (`==x.y.z`). The action is reversible. Use this when releasing a fix version that supersedes the broken one, to ensure new installs get the corrected version by default.
