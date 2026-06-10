"""The reactive layer: a FastMCP (stdio) server exposing the note tools.

The server resolves the current project by cwd at startup, builds the mount-set
index, and binds six thin tools to a :class:`VaultService`. Transport is stdio
(one session = one process, project free from cwd); the same code runs over HTTP
later by changing one run argument (decision ``stdio-transport``).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import index_path
from .index import Index
from .registry import resolve_session
from .vault import VaultService


def build_server(vault: VaultService) -> FastMCP:
    mcp = FastMCP("tremula")

    @mcp.tool()
    def write_note(
        title: str,
        content: str,
        type: str = "module",
        scope: str = "shared",
        links: dict[str, list[str]] | None = None,
    ) -> str:
        """Create or update a note in the current project's vault. Returns its memory:// URI."""
        return vault.write_note(title, content, type=type, scope=scope, links=links)

    @mcp.tool()
    def read_note(uri: str) -> dict:
        """Read one note by memory:// URI (only within the current mount set)."""
        return vault.read_note(uri)

    @mcp.tool()
    def search(query: str, scope: str | None = None) -> list[dict]:
        """Full-text search notes in the current mount set; optional scope filter."""
        return vault.search(query, scope=scope)

    @mcp.tool()
    def get_context(topic: str, depth: int = 1) -> dict:
        """Find a topic and expand the graph around it (neighbors to `depth` hops)."""
        result = vault.get_context(topic, depth=depth)
        return {"topic": result.topic, "seeds": result.seeds,
                "neighbors": result.neighbors, "content": result.content}

    @mcp.tool()
    def link_notes(src: str, dst: str, relation: str) -> str:
        """Add a typed link src --relation--> dst (depends_on/implements/decided_in/part_of)."""
        return vault.link_notes(src, dst, relation)

    @mcp.tool()
    def split_note(uri: str) -> list[str]:
        """Split an oversized note by its ## sections; parent becomes an index."""
        return vault.split_note(uri)

    return mcp


def serve() -> int:
    """Resolve the session, build the index, and run the stdio server."""
    import sys

    ctx = resolve_session()
    if not ctx.project:
        print("tremula: no registered project for cwd; run `tremula registry init`",
              file=sys.stderr)
        return 1
    index = Index(index_path(ctx.project))
    index.rebuild(ctx.mounts)
    vault = VaultService(ctx.mounts, index, project=ctx.project)
    build_server(vault).run()
    return 0
