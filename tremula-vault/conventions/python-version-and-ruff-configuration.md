---
scope: shared
source: distilled
type: convention
---

# Python version and ruff configuration

Project targets **Python 3.12+** (strict requirement in `requires-python`).

Ruff configuration:
- Line length: 100
- Selected rules: E (errors), F (pyflakes), I (imports/isort), UP (version upgrades), B (flake8-bugbear)

This is the active linting baseline for all code.
