---
scope: backend
source: distilled
type: decision
---

# Decision: Trusted Publishing via OIDC for PyPI releases

Tremula publishes to PyPI from GitHub Actions using Trusted Publisher (OIDC). Each CI run receives a short-lived token issued by PyPI from GitHub's OIDC identity; no long-lived secret is stored.

**Setup:** Configure once in PyPI project settings → Publishing, specifying the repository and workflow file. In the workflow, add `permissions: {id-token: write}` and run `uv publish --trusted-publishing always` with no `--token` flag.

**Why:** Eliminates credential storage and rotation burden. Short-lived tokens cannot be misused after the CI run ends. This is PyPI's recommended path for repeatable CI/CD releases.
