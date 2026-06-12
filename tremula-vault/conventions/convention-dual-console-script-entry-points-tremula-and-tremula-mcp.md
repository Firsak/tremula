---
scope: shared
source: distilled
type: convention
---

# Convention: Dual console-script entry points (tremula and tremula-mcp)

Both `tremula` and `tremula-mcp` console scripts are registered in `pyproject.toml` (`[project.scripts]`) and invoke `tremula.cli:main`. They are identical and interchangeable.

**Why:** The PyPI package is named `tremula-mcp`, enabling zero-install workflows (`uvx tremula-mcp <cmd>`). But locally installed CLI (`uv tool install tremula-mcp`) uses `tremula` as the command name (shorter, more natural). Supporting both entry points lets both use cases work without users having to remember different names.
