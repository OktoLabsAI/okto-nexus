"""C2 wiring: the high-volume tools accept ``profile`` and route their response
through the projection helper, INSIDE the canonical envelope, with telemetry.

Drives the real registered tool functions (via a capture-server that grabs the
``@tool_envelope``-wrapped callables) against seeded data, so the integration -
param parsing, projection, telemetry merge, canonical envelope - is exercised
end to end. Field-level projection logic itself is unit-tested in
test_mcp_projection.py.
"""

from __future__ import annotations

import asyncio

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools import events as event_tools
from okto_nexus.adapters.inbound.mcp.tools import inbox as inbox_tools


class CaptureServer:
    """Stand-in for FastMCP: ``@server.tool()`` just records the callable."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def ctx(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    srv = CaptureServer()
    inbox_tools.register(srv, deps)
    event_tools.register(srv, deps)
    # Seed an unread delivery of one message to 'rcpt' so inbox_pull returns it.
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="rcpt")
        deps.repos.agents.upsert(uow, agent_id="sender")
        uow.connection.execute(
            "INSERT OR IGNORE INTO workspaces (workspace_id, created_at) VALUES (?, ?)",
            ("ws", deps.clock.now_iso()),
        )
        deps.repos.messages.create(
            uow,
            message_id="m1",
            workspace_id="ws",
            from_agent_id="sender",
            subject="hi",
            body="hello world body",
        )
        deps.repos.deliveries.create(
            uow,
            delivery_id="d1",
            message_id="m1",
            recipient_agent_id="rcpt",
            status="unread",
        )
    return deps, srv, str(tmp_path)


def _telemetry_keys(data: dict) -> set[str]:
    return {"payload_bytes", "omitted_count", "truncated"} & set(data)


# --------------------------------------------------------------------------- #
# inbox wiring
# --------------------------------------------------------------------------- #
def test_inbox_pull_summary_projects_and_adds_telemetry(ctx):
    _, srv, _ = ctx
    env = srv.tools["inbox_pull"](agent_id="rcpt", profile="summary")
    assert env["ok"] is True
    data = env["data"]
    assert _telemetry_keys(data) == {"payload_bytes", "omitted_count", "truncated"}
    msg = data["messages"][0]
    assert msg["message_id"] == "m1"  # load-bearing kept
    assert "delivery_id" not in msg  # contextual dropped in summary
    assert msg["follow_up"]["target_ref"] == "inbox_peek"
    assert data["omitted_count"] > 0


def test_inbox_pull_default_keeps_contextuals(ctx):
    _, srv, _ = ctx
    env = srv.tools["inbox_pull"](agent_id="rcpt")  # omitted -> default
    msg = env["data"]["messages"][0]
    assert msg["message_id"] == "m1"
    assert "delivery_id" in msg and "body" in msg  # default keeps everything alive


def test_inbox_pull_full_is_raw(ctx):
    _, srv, _ = ctx
    env = srv.tools["inbox_pull"](agent_id="rcpt", profile="full")
    msg = env["data"]["messages"][0]
    assert "delivery_id" in msg and "body" in msg
    assert env["data"]["omitted_count"] == 0


def test_invalid_profile_is_canonical_validation_error(ctx):
    _, srv, _ = ctx
    env = srv.tools["inbox_peek"](agent_id="rcpt", profile="foo")
    assert env["ok"] is False
    assert env["error"]["code"] == "VALIDATION_ERROR"


def test_inbox_peek_telemetry_present(ctx):
    _, srv, _ = ctx
    env = srv.tools["inbox_peek"](agent_id="rcpt", profile="summary")
    assert env["ok"] is True
    assert _telemetry_keys(env["data"]) == {"payload_bytes", "omitted_count", "truncated"}


# --------------------------------------------------------------------------- #
# events wiring
# --------------------------------------------------------------------------- #
def test_event_get_has_telemetry_and_canonical_envelope(ctx):
    _, srv, root = ctx
    env = srv.tools["event_get"](
        project_root=root, agent_id="rcpt", stream="workspace", profile="summary"
    )
    assert env["ok"] is True
    data = env["data"]
    assert _telemetry_keys(data) == {"payload_bytes", "omitted_count", "truncated"}
    assert isinstance(data["events"], list)
    # pagination is untouched (next_cursor still part of the event payload)
    assert "next_cursor" in data


def test_event_get_invalid_profile_is_validation_error(ctx):
    _, srv, root = ctx
    env = srv.tools["event_get"](
        project_root=root, agent_id="rcpt", stream="workspace", profile="bogus"
    )
    assert env["ok"] is False
    assert env["error"]["code"] == "VALIDATION_ERROR"


def test_event_wait_snapshot_is_projected(ctx):
    # The async long-poll path (timeout_seconds=0 -> snapshot) is projected just
    # like event_get; an invalid profile fails BEFORE parking, not after.
    _, srv, root = ctx
    env = asyncio.run(
        srv.tools["event_wait"](
            project_root=root,
            agent_id="rcpt",
            stream="workspace",
            timeout_seconds=0,
            profile="summary",
        )
    )
    assert env["ok"] is True
    assert _telemetry_keys(env["data"]) == {"payload_bytes", "omitted_count", "truncated"}

    bad = asyncio.run(
        srv.tools["event_wait"](
            project_root=root, agent_id="rcpt", stream="workspace", profile="nope"
        )
    )
    assert bad["ok"] is False and bad["error"]["code"] == "VALIDATION_ERROR"
