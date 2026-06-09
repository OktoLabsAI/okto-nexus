"""Tool-schema documentation contract.

Guards the agent-facing usability of every MCP tool: each tool parameter MUST
carry a non-empty ``description`` in the published ``inputSchema`` (so a calling
agent sees what every argument means), and the two enum-shaped parameters that
gate routing - ``message_create.target`` / ``handoff_create.target`` (the
``strategy`` discriminator) and ``handoff_create.visibility`` - MUST enumerate
their allowed values in prose.

This is the regression net for the "explain every parameter, especially enums"
contract: a new tool (or a new parameter) that ships without a description fails
here instead of reaching agents undocumented.

Uses the REAL FastMCP server (built via ``create_server`` over a real migrated
temp store) so the assertions run against the exact schema agents receive. The
SDK is required for this slice; the test is skipped if it is absent.
"""

from __future__ import annotations

import asyncio

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, create_server

pytest.importorskip("mcp", reason="MCP SDK required to build the live tool schemas")


def _list_tools(tmp_path):
    """Bootstrap + build the live server and return its published tools."""
    home = tmp_path / "home"
    deps = bootstrap({"OKTO_NEXUS_HOME": str(home)}, [])
    server = create_server(deps)
    return asyncio.run(server.list_tools())


def test_every_tool_parameter_has_a_description(tmp_path):
    """No tool parameter may reach an agent without a non-empty description."""
    tools = _list_tools(tmp_path)
    assert tools, "expected the server to register at least one tool"

    undocumented: list[str] = []
    for tool in tools:
        properties = (tool.inputSchema or {}).get("properties", {})
        for name, spec in properties.items():
            description = spec.get("description")
            if not description or not str(description).strip():
                undocumented.append(f"{tool.name}.{name}")

    assert not undocumented, f"parameters missing a description: {undocumented}"


def test_routing_target_enum_is_spelled_out(tmp_path):
    """The ``target.strategy`` enum values are enumerated in the description."""
    tools = {t.name: t for t in _list_tools(tmp_path)}

    for tool_name in ("message_create", "handoff_create"):
        target = (tools[tool_name].inputSchema or {})["properties"]["target"]
        description = target.get("description", "")
        # House style (mirrors okto-pulse): enums are spelled "one of: ...".
        assert "one of:" in description, (
            f"{tool_name}.target description should enumerate strategies as 'one of: ...'"
        )
        for strategy in (
            "direct",
            "capability",
            "role",
            "broadcast",
            "mixed",
            "direct_with_fallback",
        ):
            assert strategy in description, (
                f"{tool_name}.target description omits the '{strategy}' strategy"
            )


def test_handoff_visibility_enum_is_spelled_out(tmp_path):
    """The ``visibility`` enum values are enumerated in the description."""
    tools = {t.name: t for t in _list_tools(tmp_path)}

    visibility = (tools["handoff_create"].inputSchema or {})["properties"]["visibility"]
    description = visibility.get("description", "")
    assert "one of:" in description, (
        "handoff_create.visibility description should enumerate values as 'one of: ...'"
    )
    for value in ("public", "eligible", "private"):
        assert value in description, (
            f"handoff_create.visibility description omits the '{value}' value"
        )
