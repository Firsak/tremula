"""MCP-server-level tests: the six tools exercised through FastMCP itself.

The Stage 3 suite tests VaultService directly; these go through
``build_server`` and FastMCP's tool-call layer, so schema generation, argument
validation, and error propagation are covered too.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tremula.index import Index
from tremula.server import build_server
from tremula.vault import VaultService

EXPECTED_TOOLS = {"write_note", "read_note", "search", "get_context",
                  "link_notes", "split_note"}


@pytest.fixture
def server_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TREMULA_HOME", str(tmp_path / "home"))
    vault_dir = tmp_path / "proj" / "tremula-vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "_index.md").write_text("---\ntype: index\nscope: shared\n---\n\n# P\n")
    index = Index(tmp_path / "home" / "index" / "proj.sqlite")
    mounts = {"proj": vault_dir}
    index.rebuild(mounts)
    vault = VaultService(mounts, index, project="proj")
    return build_server(vault), vault


def _result(raw):
    """Unwrap FastMCP call_tool output.

    str/list-returning tools come back as ``(content, {"result": ...})``;
    bare-dict-returning tools come back unstructured, as JSON text in a
    TextContent block — exactly what a real MCP client would parse.
    """
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], dict):
        return raw[1].get("result", raw[1])
    if isinstance(raw, list) and raw and hasattr(raw[0], "text"):
        try:
            return json.loads(raw[0].text)
        except (json.JSONDecodeError, TypeError):
            return raw[0].text
    return raw


def test_all_six_tools_registered(server_setup):
    mcp, _ = server_setup
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for tool in tools:  # every tool must carry a docstring-derived description
        assert tool.description


def test_write_search_read_roundtrip(server_setup):
    mcp, _ = server_setup

    async def go():
        uri = _result(await mcp.call_tool(
            "write_note",
            {"title": "Queue design", "content": "We use a redis stream.",
             "type": "architecture"},
        ))
        hits = _result(await mcp.call_tool("search", {"query": "redis stream"}))
        note = _result(await mcp.call_tool("read_note", {"uri": uri}))
        return uri, hits, note

    uri, hits, note = asyncio.run(go())
    assert uri == "memory://proj/architecture/queue-design"
    assert hits and hits[0]["uri"] == uri
    assert "redis stream" in note["body"]


def test_link_and_context_through_server(server_setup):
    mcp, _ = server_setup

    async def go():
        a = _result(await mcp.call_tool(
            "write_note", {"title": "Billing", "content": "stripe charges",
                           "type": "module"}))
        b = _result(await mcp.call_tool(
            "write_note", {"title": "Webhooks", "content": "receives events",
                           "type": "module"}))
        await mcp.call_tool("link_notes", {"src": b, "dst": a, "relation": "depends_on"})
        ctx = _result(await mcp.call_tool(
            "get_context", {"topic": "stripe charges", "depth": 1}))
        return a, b, ctx

    a, b, ctx = asyncio.run(go())
    assert a in ctx["seeds"]
    assert b in ctx["neighbors"]


def test_out_of_mount_read_surfaces_error(server_setup):
    mcp, _ = server_setup
    with pytest.raises(Exception, match="mount set"):
        asyncio.run(mcp.call_tool("read_note", {"uri": "memory://other/modules/x"}))


def test_traversal_uri_surfaces_error_not_file(server_setup):
    mcp, _ = server_setup
    with pytest.raises(Exception, match="(invalid path segment|not a valid)"):
        asyncio.run(mcp.call_tool("read_note", {"uri": "memory://proj/../secret"}))


def test_split_note_through_server(server_setup):
    mcp, _ = server_setup

    async def go():
        uri = _result(await mcp.call_tool("write_note", {
            "title": "Long doc",
            "content": "# Long doc\n\nintro\n\n## A\n\naaa\n\n## B\n\nbbb\n",
            "type": "architecture"}))
        children = _result(await mcp.call_tool("split_note", {"uri": uri}))
        parent = _result(await mcp.call_tool("read_note", {"uri": uri}))
        return children, parent

    children, parent = asyncio.run(go())
    assert len(children) == 2
    assert "intro" in parent["body"]
