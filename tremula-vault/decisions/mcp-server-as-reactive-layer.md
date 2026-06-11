---
scope: shared
source: distilled
type: decision
---

# MCP server as reactive layer

Tremula runs as an MCP server (FastMCP, `mcp>=1.2.0`) and exposes tools: `search`, `get_context`, `read_note`, `write_note`, `link_notes`, `split_note`.

This allows Claude Code to query and update the vault atomically via tool calls, decoupling note graph maintenance from file system I/O.
