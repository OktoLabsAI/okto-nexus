"""Frente 1 (compaction) — Card T2, scenarios S2 + S3.

S2 (AC2/AC3) — SCHEMA-level compaction contract of the published MCP surface:

* every tool ``description`` is a single compact line: <= 200 characters AND
  free of any newline character (the slimmed, agent-facing one-liner);
* every parameter in every tool ``inputSchema['properties']`` still carries a
  non-empty ``description`` (no argument reaches an agent undocumented);
* the routing ``target`` description on ``message_create`` and
  ``handoff_create`` keeps the inline strategy SHAPES so a harness without
  resources can still target correctly (S7): each carries the literal
  ``"strategy":"direct"`` and ``"strategy":"capability"`` JSON snippets and
  points to the shared ``okto-nexus://reference/target-grammar`` resource.
  ``handoff_create`` additionally advertises ``direct_with_fallback`` (a
  handoff-only strategy), while ``message_create`` must NOT — message_create
  rejects that strategy.

S3 (AC4) — the pre-S3 ``message_get`` / ``message_list`` / ``message_wait``
clean-break shims answer the canonical envelope with ``ok:false`` and
``error['code'] == 'MIGRATED'``, naming a concrete replacement (an ``inbox``
tool), and crucially NOT an opaque unknown-tool failure.

Built against the REAL FastMCP server (``create_server`` over a real migrated
temp store) so the assertions run against the exact schema/behaviour agents
receive, mirroring the helpers in ``tests/test_tools_surface.py`` and
``tests/test_tool_schemas.py``. Skipped when the MCP SDK is absent.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, create_server

pytest.importorskip("mcp", reason="MCP SDK required to build/call the live tool surface")


# --------------------------------------------------------------------------- #
# Helpers — mirrored from tests/test_tools_surface.py / test_tool_schemas.py
# --------------------------------------------------------------------------- #
@pytest.fixture
def surface(tmp_path):
    """A live FastMCP server over a real migrated store + a real project dir."""
    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    server = create_server(deps)
    project = tmp_path / "project"
    project.mkdir()
    return server, str(project)


def _list_tools(server):
    """Return the live server's published tools."""
    return asyncio.run(server.list_tools())


def _call(server, name: str, arguments: dict | None = None) -> dict:
    """Call a tool through FastMCP (schema validation included); return the envelope."""
    result = asyncio.run(server.call_tool(name, arguments or {}))
    if isinstance(result, tuple):  # (unstructured, structured) when output schema exists
        return result[1]
    block = result[0]
    return json.loads(block.text)


# --------------------------------------------------------------------------- #
# S2 (AC2/AC3): compact, single-line descriptions; every param documented
# --------------------------------------------------------------------------- #
def test_s2_every_tool_description_is_compact_single_line(surface):
    """Every published tool description is <= 200 chars and has no newline."""
    server, _ = surface
    tools = _list_tools(server)
    assert tools, "expected the server to register at least one tool"

    too_long: list[str] = []
    multiline: list[str] = []
    for tool in tools:
        description = tool.description or ""
        if len(description) > 200:
            too_long.append(f"{tool.name} ({len(description)} chars)")
        if "\n" in description:
            multiline.append(tool.name)

    assert not too_long, f"tool descriptions exceeding 200 chars: {too_long}"
    assert not multiline, f"tool descriptions containing a newline: {multiline}"


def test_s2_every_tool_parameter_has_a_description(surface):
    """No tool parameter may reach an agent without a non-empty description."""
    server, _ = surface
    tools = _list_tools(server)
    assert tools, "expected the server to register at least one tool"

    undocumented: list[str] = []
    for tool in tools:
        properties = (tool.inputSchema or {}).get("properties", {})
        for name, spec in properties.items():
            description = spec.get("description")
            if not description or not str(description).strip():
                undocumented.append(f"{tool.name}.{name}")

    assert not undocumented, f"parameters missing a description: {undocumented}"


def test_s2_target_descriptions_keep_strategy_shapes_and_grammar_pointer(surface):
    """Both target-taking tools keep inline strategy shapes + the shared grammar
    pointer; only handoff_create advertises direct_with_fallback."""
    server, _ = surface
    tools = {t.name: t for t in _list_tools(server)}

    for tool_name in ("message_create", "handoff_create"):
        target = (tools[tool_name].inputSchema or {})["properties"]["target"]
        description = target.get("description", "")
        assert '"strategy":"direct"' in description, (
            f'{tool_name}.target must keep the literal "strategy":"direct" shape'
        )
        assert '"strategy":"capability"' in description, (
            f'{tool_name}.target must keep the literal "strategy":"capability" shape'
        )
        assert "okto-nexus://reference/target-grammar" in description, (
            f"{tool_name}.target must point to the shared target-grammar resource"
        )

    msg_target = (tools["message_create"].inputSchema or {})["properties"]["target"]
    handoff_target = (tools["handoff_create"].inputSchema or {})["properties"]["target"]
    msg_desc = msg_target.get("description", "")
    handoff_desc = handoff_target.get("description", "")

    assert "direct_with_fallback" in handoff_desc, (
        "handoff_create.target must advertise the direct_with_fallback strategy"
    )
    assert "direct_with_fallback" not in msg_desc, (
        "message_create.target must NOT advertise direct_with_fallback "
        "(message_create rejects that strategy)"
    )


# --------------------------------------------------------------------------- #
# S3 (AC4): the pre-S3 message_* shims answer a prescriptive MIGRATED envelope
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shim", ["message_get", "message_list", "message_wait"])
def test_s3_message_shim_returns_migrated_naming_an_inbox_replacement(surface, shim):
    """Each pre-S3 shim returns the canonical envelope ok:false code=MIGRATED,
    names an 'inbox' replacement, and is NOT an opaque unknown-tool failure."""
    server, _ = surface

    env = _call(server, shim)

    # Canonical envelope, not an exception or SDK error grammar.
    assert env["ok"] is False, f"{shim} must answer with a canonical envelope"
    error = env["error"]
    assert error["code"] == "MIGRATED", (
        f"{shim} must answer code=MIGRATED, got: {error}"
    )

    # The error must name a concrete replacement: an inbox tool, surfaced in the
    # human message and/or the structured details.
    message = error.get("message", "") or ""
    details = error.get("details", {}) or {}
    details_text = json.dumps(details)
    assert "inbox" in message or "inbox" in details_text, (
        f"{shim} MIGRATED error must name an inbox replacement tool: {error}"
    )

    # Crucially NOT an unknown-tool error: the shim is a registered tool that
    # prescribes the migration, never an opaque 'unknown tool' failure.
    assert error["code"] != "UNKNOWN_TOOL"
    assert "unknown tool" not in message.lower(), (
        f"{shim} must land on the MIGRATED shim, not an unknown-tool error: {error}"
    )
