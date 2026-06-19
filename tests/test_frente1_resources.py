"""Frente 1 (residente) - MCP reference resources + envelope byte-compat.

Card T1, scenarios S1 (AC1) and S6 (AC7).

The deep reference prose that Frente 1 relocated out of ``SERVER_INSTRUCTIONS``
and the per-tool descriptions now lives behind ``resources/read`` as a CLOSED
set of ``okto-nexus://reference/*`` URIs (BR9). These tests run against the REAL
FastMCP server (``create_server`` over a real migrated temp store) - the exact
surface an agent sees:

* S1: ``list_resources`` advertises EXACTLY the 10 reference URIs (no missing,
  no extra) and EACH ``read_resource`` returns non-empty content carrying the
  ``version:`` frontmatter near the start (so a client can detect a stale cache).
* S6: representative tool calls return the canonical envelope unchanged -
  success ``{ok:true,data:{...}}`` / failure ``{ok:false,error:{code,message}}``;
  in particular ``nexus_info`` is a success with a dict ``data`` and the
  ``message_get`` migration shim answers ``MIGRATED`` (a prescriptive replacement
  pointer), NOT an opaque unknown-tool error.

Mirrors the build/list/call helpers in ``tests/test_tools_surface.py`` and
``tests/test_tool_schemas.py``.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, create_server

pytest.importorskip("mcp", reason="MCP SDK required to build the live server")


# The closed set of reference resource URIs (BR9). Exactly these 10, no more.
EXPECTED_RESOURCE_URIS = {
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


@pytest.fixture
def surface(tmp_path):
    """A live FastMCP server over a real migrated store + a real project dir."""
    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    server = create_server(deps)
    project = tmp_path / "project"
    project.mkdir()
    return server, str(project)


def _call(server, name: str, arguments: dict | None = None) -> dict:
    """Call a tool through FastMCP (schema validation included); return the envelope."""
    result = asyncio.run(server.call_tool(name, arguments or {}))
    if isinstance(result, tuple):  # (unstructured, structured) when output schema exists
        return result[1]
    block = result[0]
    return json.loads(block.text)


def _read_body(server, uri: str) -> str:
    """Read a resource and return its single text body (the verbatim content)."""
    contents = list(asyncio.run(server.read_resource(uri)))
    assert contents, f"{uri} returned no content blocks"
    body = contents[0].content
    assert isinstance(body, str), f"{uri} content must be text, got {type(body)!r}"
    return body


def _assert_canonical_envelope(env: dict, *, where: str) -> None:
    """Assert ``env`` is a canonical envelope (success XOR failure shape)."""
    assert isinstance(env, dict), f"{where}: response must be a dict, got {env!r}"
    assert env.get("ok") in (True, False), f"{where}: 'ok' must be a bool: {env!r}"
    if env["ok"] is True:
        assert isinstance(env.get("data"), dict), (
            f"{where}: success envelope must carry a dict 'data': {env!r}"
        )
        assert "error" not in env, (
            f"{where}: success envelope must NOT carry 'error': {env!r}"
        )
    else:
        assert "data" not in env, (
            f"{where}: failure envelope must NOT carry 'data': {env!r}"
        )
        error = env.get("error")
        assert isinstance(error, dict), f"{where}: failure must carry 'error' dict: {env!r}"
        assert isinstance(error.get("code"), str) and error["code"], (
            f"{where}: error.code must be a non-empty str: {env!r}"
        )
        assert isinstance(error.get("message"), str) and error["message"], (
            f"{where}: error.message must be a non-empty str: {env!r}"
        )


# --------------------------------------------------------------------------- #
# S1 (AC1): the reference resources are a closed set of 10, each versioned.
# --------------------------------------------------------------------------- #
def test_list_resources_advertises_exactly_the_ten_reference_uris(surface):
    server, _ = surface

    resources = asyncio.run(server.list_resources())
    # AnyUrl may normalise; compare on stringified URIs (defend against a stray
    # trailing slash across pydantic versions - none of the expected URIs end in
    # one, so stripping is safe).
    advertised = {str(r.uri).rstrip("/") for r in resources}

    assert advertised == EXPECTED_RESOURCE_URIS, (
        "list_resources must advertise EXACTLY the closed reference set. "
        f"missing={EXPECTED_RESOURCE_URIS - advertised} "
        f"extra={advertised - EXPECTED_RESOURCE_URIS}"
    )
    # Closed set => exactly ten distinct URIs (no duplicates collapsing the set).
    assert len(advertised) == 10
    assert len(list(resources)) == 10, "no duplicate resource registrations"


def test_each_reference_resource_reads_nonempty_with_version_frontmatter(surface):
    server, _ = surface

    for uri in EXPECTED_RESOURCE_URIS:
        body = _read_body(server, uri)
        assert body.strip(), f"{uri} returned empty content"
        # The frontmatter sits at the very top: ``---\nversion: "N"\n---``.
        head = body[:80]
        assert "version:" in head, (
            f"{uri} body must carry 'version:' frontmatter near the start; "
            f"head was {head!r}"
        )


# --------------------------------------------------------------------------- #
# S6 (AC7): canonical envelope byte-compat on representative tool calls.
# --------------------------------------------------------------------------- #
def test_nexus_info_returns_success_envelope_with_dict_data(surface):
    server, _ = surface

    env = _call(server, "nexus_info")
    _assert_canonical_envelope(env, where="nexus_info")
    assert env["ok"] is True
    assert isinstance(env["data"], dict) and env["data"], (
        "nexus_info must return a non-empty data dict"
    )


def test_message_get_shim_returns_migrated_not_unknown_tool(surface):
    server, _ = surface

    env = _call(server, "message_get")
    _assert_canonical_envelope(env, where="message_get")
    assert env["ok"] is False
    # The shim is PUBLISHED: a prescriptive MIGRATED, never an opaque
    # unknown-tool / tool-not-found error (which is what a removed tool would
    # surface to a pre-S3 client).
    assert env["error"]["code"] == "MIGRATED", (
        f"message_get must answer MIGRATED, got {env['error']['code']!r}: {env}"
    )


def test_representative_success_tool_returns_canonical_envelope(surface):
    """A real workspace-scoped tool (not just the meta tool) honours the envelope."""
    server, project = surface

    env = _call(server, "workspace_resolve", {"project_root": project})
    _assert_canonical_envelope(env, where="workspace_resolve")
    assert env["ok"] is True
    assert env["data"], "workspace_resolve success data must be populated"


def test_other_migration_shims_also_return_canonical_migrated(surface):
    """message_list / message_wait round out the migrated shim envelope set."""
    server, _ = surface

    for shim in ("message_list", "message_wait"):
        env = _call(server, shim)
        _assert_canonical_envelope(env, where=shim)
        assert env["ok"] is False
        assert env["error"]["code"] == "MIGRATED", (
            f"{shim} must answer MIGRATED, got {env['error']['code']!r}: {env}"
        )
