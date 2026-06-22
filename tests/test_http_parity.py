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


def _resource_uris(server) -> set[str]:
    resources = asyncio.run(server.list_resources())
    return {str(r.uri) for r in resources}


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


def test_http_advertises_the_same_reference_resources_as_stdio(tmp_path):
    """The on-demand reference docs MUST be reachable over HTTP too: an agent
    connects over THIS transport and the inline instructions point it at
    okto-nexus://reference/* (monitoring/preflight/...). Regression guard for the
    bug where create_http_mcp_server registered tools but NOT resources, so every
    resources/read returned 'Unknown resource' over the serve.
    """
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])

    stdio_uris = _resource_uris(create_server(deps))
    http_uris = _resource_uris(create_http_mcp_server(deps))

    assert http_uris == stdio_uris  # same closed reference set on both transports
    # Non-trivial + the specific URI the failing agent could not read.
    assert "okto-nexus://reference/monitoring" in http_uris
    assert "okto-nexus://reference/preflight" in http_uris
    assert len(http_uris) >= 5
