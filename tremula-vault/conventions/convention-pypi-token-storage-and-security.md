---
scope: shared
source: manual
type: convention
---

# Convention: PyPI publishing — twine + ~/.pypirc

**Canonical local publish command:**

```bash
uvx twine upload dist/*
```

twine reads `~/.pypirc` natively and picks up the `[pypi]` token automatically.
**`uv publish` deliberately ignores `.pypirc`** — do not use it for publishing
unless bridging the token explicitly via `UV_PUBLISH_TOKEN` (an earlier session
did this and it works, but it re-derives what twine does out of the box).

**Credential home:** `~/.pypirc` in the HOME directory (never inside any
repository), `[pypi]` section, `username = __token__`, `password = pypi-...`.
Tokens are bearer credentials equivalent to passwords: never commit them, never
put them in env files inside a repo, never echo them into logs.

**Scoping:** account-scoped token only for a project's first upload; once the
project exists on PyPI, switch to a project-scoped token (tied to
`tremula-mcp`) and delete the account-scoped one.

**CI path:** GitHub Actions releases use Trusted Publishing (OIDC) instead of
any stored token — see [[decisions/decision-trusted-publishing-via-oidc-for-pypi-releases]].

> History: two sessions gave conflicting advice (twine vs `uv publish` +
> token-bridge) because this note originally captured only the token-handling
> pattern, not the tool decision. Ratified by the user 2026-06-12: twine is
> canonical for local publishes.
