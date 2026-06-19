"""Frente 1 token-reduction HARNESS gate - Card T4, scenarios S7 + S8.

These tests defend the owner's lock for the residente token-reduction work:
*assertividade de uso > economia de tokens*. The deep reference prose moved to
MCP ``resources/read`` (okto-nexus://reference/...), but the INLINE ``tools/list``
surface must still let an agent that sees ONLY the inline schema call every tool
correctly on the FIRST try, and ``nexus_info`` must expose the stale-cache signal
(surface_revision + resource_versions) so a client can detect a drifted cache.

S7 (lock guard, AC2/AC6) - the STRUCTURAL proxy for "a harness with NO MCP
resources can still target the 6 canonical tasks". The whole point is to assert
the inline surface is self-sufficient, so these assertions read ONLY
``server.list_tools()`` - they NEVER do a ``resources/read`` (that would defeat
the gate). Mirrors the live-server build used by ``test_tool_schemas.py``.

S8 (AC1) - ``nexus_info`` reports an integer ``surface_revision`` and a
``resource_versions`` ``{uri: version}`` map over the 10 reference resources, and
those two signals let a client holding a stale cache DETECT divergence. Calls the
tool through the same FastMCP path as ``test_tools_surface.py`` (the ``_call``
helper is copied verbatim from that file).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from okto_nexus.adapters.inbound.mcp.server import (
    SURFACE_REVISION,
    bootstrap,
    create_server,
)

pytest.importorskip("mcp", reason="MCP SDK required to build/call the live surface")


# --------------------------------------------------------------------------- #
# Live-server harness helpers (mirrors tests/test_tools_surface.py &
# tests/test_tool_schemas.py: a real bootstrap + create_server over a temp home).
# --------------------------------------------------------------------------- #
@pytest.fixture
def surface(tmp_path):
    """A live FastMCP server over a real migrated store + a real project dir."""
    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    server = create_server(deps)
    project = tmp_path / "project"
    project.mkdir()
    return server, str(project)


def _call(server, name: str, arguments: dict | None = None) -> dict:
    """Call a tool through FastMCP (schema validation included); return the envelope.

    Copied verbatim from tests/test_tools_surface.py so S8 exercises the exact
    validation path agents hit.
    """
    result = asyncio.run(server.call_tool(name, arguments or {}))
    if isinstance(result, tuple):  # (unstructured, structured) when output schema exists
        return result[1]
    block = result[0]
    return json.loads(block.text)


def _tools_by_name(server) -> dict:
    """Return the published {tool_name: tool} from the live INLINE surface only."""
    return {t.name: t for t in asyncio.run(server.list_tools())}


def _properties(tool) -> dict:
    """The published inputSchema properties (name -> spec) for a tool."""
    return (tool.inputSchema or {}).get("properties", {})


def _described(tool, param: str) -> str:
    """Return ``param``'s non-empty description, asserting it is present."""
    spec = _properties(tool).get(param)
    assert spec is not None, f"{tool.name} must publish a '{param}' parameter inline"
    description = spec.get("description")
    assert description and str(description).strip(), (
        f"{tool.name}.{param} must carry a non-empty inline description"
    )
    return description


# The closed set of reference resources nexus_info must report (BR9: 10 URIs).
_EXPECTED_RESOURCE_URIS = {
    "okto-nexus://reference/preflight",
    "okto-nexus://reference/communication",
    "okto-nexus://reference/monitoring",
    "okto-nexus://reference/target-grammar",
    "okto-nexus://reference/tool-docs/messages",
    "okto-nexus://reference/tool-docs/inbox",
    "okto-nexus://reference/tool-docs/events",
    "okto-nexus://reference/tool-docs/handoff",
    "okto-nexus://reference/tool-docs/identity",
    "okto-nexus://reference/tool-docs/artifacts",
}


# --------------------------------------------------------------------------- #
# S7 (AC2/AC6): inline tools/list is sufficient for the 6 canonical tasks.
# NOTE: every assertion below reads ONLY list_tools() - NO resources/read.
# --------------------------------------------------------------------------- #
def test_s7_ta_direct_message_targetable_from_inline_surface(surface):
    """(Ta) Send a DIRECT message: message_create exists, its required params are
    each described, and the target description carries the direct strategy shape."""
    server, _ = surface
    tools = _tools_by_name(server)

    assert "message_create" in tools, "message_create must be on the inline surface"
    create = tools["message_create"]

    # The four required params an agent must fill are each documented inline.
    for required in ("project_root", "from_agent_id", "subject", "body"):
        _described(create, required)
    # And they are actually marked required in the published schema.
    schema_required = set((create.inputSchema or {}).get("required", []))
    assert {"project_root", "from_agent_id", "subject", "body"} <= schema_required, (
        "message_create must mark project_root/from_agent_id/subject/body required"
    )

    target_desc = _described(create, "target")
    assert '"strategy":"direct"' in target_desc, (
        "message_create.target must spell the direct strategy shape inline so a "
        "resource-less harness can target one agent"
    )


def test_s7_tb_broadcast_message_targetable_from_inline_surface(surface):
    """(Tb) Broadcast: message_create.target mentions the broadcast strategy."""
    server, _ = surface
    tools = _tools_by_name(server)

    target_desc = _described(tools["message_create"], "target")
    assert "broadcast" in target_desc, (
        "message_create.target must mention 'broadcast' inline (omit-to-broadcast "
        "is the canonical announcement path)"
    )


def test_s7_tc_capability_handoff_targetable_from_inline_surface(surface):
    """(Tc) Dispatch a capability handoff: handoff_create.target carries the
    capability strategy shape inline."""
    server, _ = surface
    tools = _tools_by_name(server)

    assert "handoff_create" in tools, "handoff_create must be on the inline surface"
    target_desc = _described(tools["handoff_create"], "target")
    assert '"strategy":"capability"' in target_desc, (
        "handoff_create.target must spell the capability strategy shape inline so "
        "a resource-less harness can dispatch by capability"
    )


def test_s7_td_event_monitoring_callable_from_inline_surface(surface):
    """(Td) Monitor the bus: event_cursor AND event_wait exist with a described
    'stream' param (anchor-then-wait, both inline)."""
    server, _ = surface
    tools = _tools_by_name(server)

    for tool_name in ("event_cursor", "event_wait"):
        assert tool_name in tools, f"{tool_name} must be on the inline surface"
        _described(tools[tool_name], "stream")


def test_s7_te_inbox_reception_loop_callable_from_inline_surface(surface):
    """(Te) Receive messages: inbox_pull AND inbox_ack exist with a described
    'agent_id' param (the pull -> ack reception loop, both inline)."""
    server, _ = surface
    tools = _tools_by_name(server)

    for tool_name in ("inbox_pull", "inbox_ack"):
        assert tool_name in tools, f"{tool_name} must be on the inline surface"
        _described(tools[tool_name], "agent_id")


def test_s7_tf_channel_posting_callable_from_inline_surface(surface):
    """(Tf) Post into a channel: channel_create exists and message_create exposes
    a described 'channel_id' param inline."""
    server, _ = surface
    tools = _tools_by_name(server)

    assert "channel_create" in tools, "channel_create must be on the inline surface"
    _described(tools["message_create"], "channel_id")


# --------------------------------------------------------------------------- #
# S8 (AC1): nexus_info exposes the stale-cache signal.
# --------------------------------------------------------------------------- #
def test_s8_nexus_info_reports_surface_revision_and_resource_versions(surface):
    """nexus_info -> surface_revision (int) + resource_versions ({uri: version}
    over the 10 reference resources, each version a non-empty string)."""
    server, _ = surface

    env = _call(server, "nexus_info")
    assert env["ok"] is True, f"nexus_info must succeed: {env}"
    data = env["data"]

    # surface_revision is an int (and matches the module constant).
    assert isinstance(data["surface_revision"], int), (
        "surface_revision must be an int so a client can compare cached vs live"
    )
    assert data["surface_revision"] == SURFACE_REVISION

    # resource_versions maps each of the 10 reference URIs to a version string.
    rv = data["resource_versions"]
    assert isinstance(rv, dict), "resource_versions must be a dict"
    assert set(rv) == _EXPECTED_RESOURCE_URIS, (
        f"resource_versions must map exactly the 10 reference URIs; "
        f"got {sorted(rv)}"
    )
    for uri, version in rv.items():
        assert uri.startswith("okto-nexus://reference/")
        assert isinstance(version, str) and version.strip(), (
            f"resource_versions[{uri}] must be a non-empty version string"
        )


def _cache_stale(cached: tuple, live: tuple) -> bool:
    """A client's staleness check: the cache is stale iff its (surface_revision,
    resource_versions) snapshot differs from the live nexus_info signal."""
    return cached != live


def test_s8_stale_cache_divergence_is_detectable(surface):
    """nexus_info is a STABLE signal a client can cache: repeated reads agree, an
    unchanged cache is NOT flagged stale, and a drifted revision/version IS.

    The non-trivial property is STABILITY/determinism - if nexus_info returned a
    different surface_revision or resource_versions on each call, caching it
    would be useless and stale-detection would false-positive. That is what
    makes the signal a usable stale-cache anchor (not the tautology that two
    different numbers compare unequal).
    """
    server, _ = surface

    def snapshot() -> tuple:
        data = _call(server, "nexus_info")["data"]
        # order-independent, hashable freeze of the {uri: version} map
        return data["surface_revision"], tuple(sorted(data["resource_versions"].items()))

    live = snapshot()

    # 1) STABILITY: nexus_info is deterministic, so a cached snapshot stays valid
    #    across reads - this is the property that makes a client cache meaningful.
    assert snapshot() == live, "nexus_info must report a stable signal across calls"

    # 2) No false positive: an unchanged cache is NOT flagged stale.
    assert not _cache_stale(live, live)

    rev, versions = live
    # 3) A client whose cached surface_revision drifted detects staleness.
    assert _cache_stale((rev - 1, versions), live)

    # 4) A client whose cached resource_versions drifted on one URI detects it.
    drifted = dict(versions)
    one_uri = sorted(drifted)[0]
    drifted[one_uri] = drifted[one_uri] + "-old"
    assert _cache_stale((rev, tuple(sorted(drifted.items()))), live)
