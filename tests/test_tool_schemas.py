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

It also guards the M3 safe-by-default surface at the SCHEMA level: the shared
target type-sentence on message_create/handoff_create, the non-string
handoff_create.payload, event_wait's snapshot default, the S3 migration shims
and the nexus_info meta tool. The BEHAVIOUR of those fixes is covered in
``test_tools_surface.py``.

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


#: The SAME concept (a routing target) must carry the SAME type guidance on
#: both tools that take one (uniform surface for agents).
_TARGET_TYPE_SENTENCE = (
    'Pass target as a raw JSON OBJECT (dict), e.g. {"strategy": "direct", '
    '"agent_id": "<id>"} - NOT as a JSON-encoded string.'
)


def test_target_type_documented_identically_on_both_tools(tmp_path):
    """message_create.target and handoff_create.target share the type sentence."""
    tools = {t.name: t for t in _list_tools(tmp_path)}

    for tool_name in ("message_create", "handoff_create"):
        target = (tools[tool_name].inputSchema or {})["properties"]["target"]
        description = target.get("description", "")
        assert _TARGET_TYPE_SENTENCE in description, (
            f"{tool_name}.target description must carry the shared JSON-object "
            "type sentence (uniform typing of the same concept)"
        )


def test_handoff_payload_schema_accepts_non_strings(tmp_path):
    """handoff_create.payload is NOT constrained to a string in the schema.

    A dict/list payload must validate as-is (the application serialises it);
    forcing the LLM to JSON-escape dicts was the bug.
    """
    tools = {t.name: t for t in _list_tools(tmp_path)}

    payload = (tools["handoff_create"].inputSchema or {})["properties"]["payload"]
    assert payload.get("type") != "string", (
        "handoff_create.payload must not be string-typed; dicts are accepted"
    )
    assert "anyOf" not in payload, (
        "handoff_create.payload must be unconstrained (Any) so raw JSON "
        "objects/arrays/strings all validate"
    )


def test_event_wait_timeout_schema_defaults_to_snapshot(tmp_path):
    """event_wait.timeout_seconds defaults to 0 (snapshot); blocking is opt-in."""
    tools = {t.name: t for t in _list_tools(tmp_path)}

    spec = (tools["event_wait"].inputSchema or {})["properties"]["timeout_seconds"]
    assert spec.get("default") == 0, (
        "event_wait.timeout_seconds must default to 0 (non-blocking snapshot)"
    )
    description = spec.get("description", "")
    assert "non-blocking" in description.lower(), (
        "event_wait.timeout_seconds description must state the default is a "
        "non-blocking snapshot"
    )
    assert "OPTS IN" in description, (
        "event_wait.timeout_seconds description must mark >0 blocking as opt-in"
    )


def test_migration_shims_are_published_with_pointers(tmp_path):
    """The S3 shims exist and their descriptions name the replacement tools."""
    tools = {t.name: t for t in _list_tools(tmp_path)}

    expectations = {
        "message_get": "inbox_pull",
        "message_list": "inbox_history",
        "message_wait": "inbox_count",
    }
    for shim, replacement in expectations.items():
        assert shim in tools, f"migration shim {shim} is not published"
        description = tools[shim].description or ""
        assert "MIGRATED" in description, (
            f"{shim} description must say it is MIGRATED"
        )
        assert replacement in description, (
            f"{shim} description must point at {replacement}"
        )


def test_nexus_info_is_published(tmp_path):
    """nexus_info exists and documents the three version fields it returns."""
    tools = {t.name: t for t in _list_tools(tmp_path)}

    assert "nexus_info" in tools, "nexus_info meta tool is not published"
    description = tools["nexus_info"].description or ""
    for field in ("package_version", "schema_version", "surface_revision"):
        assert field in description, f"nexus_info description omits {field}"
