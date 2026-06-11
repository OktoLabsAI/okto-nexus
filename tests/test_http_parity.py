"""stdio x HTTP tool-surface parity (spec S1, TS9 / rule br_167701f9).

The HTTP MCP server is built from the SAME ``register_tools`` /
``register_meta_tools`` as stdio, so parity should hold by construction -
this test is the tripwire that keeps it that way: names, parameter schemas
and descriptions must be IDENTICAL across transports.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("mcp")

from okto_nexus.adapters.inbound.http.app import create_http_mcp_server
from okto_nexus.adapters.inbound.mcp.server import bootstrap, create_server


def _tool_table(server) -> dict[str, dict]:
    tools = asyncio.run(server.list_tools())
    return {
        tool.name: {
            "description": tool.description,
            "inputSchema": tool.inputSchema,
        }
        for tool in tools
    }


def test_http_surface_is_identical_to_stdio(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])

    stdio_table = _tool_table(create_server(deps))
    http_table = _tool_table(create_http_mcp_server(deps))

    assert set(stdio_table) == set(http_table)  # same tool names
    for name in stdio_table:
        assert stdio_table[name]["inputSchema"] == http_table[name]["inputSchema"], name
        assert stdio_table[name]["description"] == http_table[name]["description"], name
    # The surface is non-trivial (all V1 tools + nexus_info present).
    assert "nexus_info" in stdio_table
    assert len(stdio_table) >= 30
