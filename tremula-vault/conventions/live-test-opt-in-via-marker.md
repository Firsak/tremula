---
scope: shared
source: distilled
type: convention
---

# Live test opt-in via marker

Tests that call external LLMs are marked with `@pytest.mark.live` and skipped by default.

Enable with `TREMULA_LIVE_TESTS=1 uv run pytest` (or export the env var).

Rationale: Avoid unnecessary API costs and external dependencies in CI/normal runs.
