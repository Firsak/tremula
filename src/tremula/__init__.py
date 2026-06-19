"""Tremula — self-maintaining code memory for AI coding agents, over MCP.

A per-project Obsidian-compatible markdown vault (``ramet``) describing a
codebase, federated across projects via a registry and bridge vaults
(``roots``). A reactive MCP server (any MCP client) serves the notes; an
ambient hooks loop (Claude Code today) captures sessions, injects context,
and distills durable knowledge in the background.

Markdown is the source of truth; the SQLite index is a rebuildable cache.
"""

__version__ = "0.1.6"
