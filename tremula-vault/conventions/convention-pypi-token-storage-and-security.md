---
scope: backend
source: distilled
type: convention
---

# Convention: PyPI token storage and security

PyPI tokens are bearer credentials equivalent to passwords. Never commit them to the repository (no `.pypirc`, no env files, no `pyproject.toml`) or set them in CI secrets visible in logs.

**Token format:** `pypi-AgE...` (the entire string including the `pypi-` prefix).

**Scoping:** Use an account-scoped token for the first upload. Once the project exists on PyPI, immediately create a project-scoped token tied to the `tremula-mcp` package only and delete the account-scoped one.

**Local publishing (development-only):** If needed, paste at run time to avoid persisting to disk: `read -rs UV_PUBLISH_TOKEN && export UV_PUBLISH_TOKEN && uv publish && unset UV_PUBLISH_TOKEN`. Alternatively, use OS keyring via the `keyring` package (encrypted, survives reboots).
