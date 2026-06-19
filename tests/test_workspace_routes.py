"""HTTP surface for the Workspaces panel: rich list + path gating + analytics
endpoint (window validation, empty workspace, canonical envelope).

Scenario coverage (spec bf6e06dc):
* S1/AC1  - GET /workspaces lists ALL known workspaces with the FR2 fields
* S2/AC2  - root_realpath gated by expose_workspace_path (off->redacted, on->shown)
* S5/AC4  - invalid window -> INVALID_WINDOW; empty workspace -> 200 zeros
* S12/AC12 - canonical {ok,...} envelope on both routes
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.domain.base import new_id, utc_now_iso  # noqa: E402

# A loopback client host so the same-machine "local_open" rule lets the REST
# surface answer without an API key (the operator owns the box).
LOOPBACK = ("127.0.0.1", 51234)


@pytest.fixture
def ctx(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    app.state.default_workspace_id = "ws-a"
    with TestClient(app, client=LOOPBACK) as client:
        yield deps, client


def setup_workspace(deps, wid, *, display_name=None, root_realpath=None):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(
            uow,
            workspace_id=wid,
            display_name=display_name,
            root_realpath=root_realpath,
            last_seen_at=utc_now_iso(),
        )


def seed_message(deps, *, wid, agent, body):
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id=agent)
        deps.repos.messages.create(
            uow,
            message_id=new_id("msg"),
            workspace_id=wid,
            from_agent_id=agent,
            body=body,
            created_at=utc_now_iso(),
        )


# --------------------------------------------------------------------------- #
# S1 / AC1 - rich list of all workspaces
# --------------------------------------------------------------------------- #
def test_list_workspaces(ctx):
    deps, client = ctx
    setup_workspace(deps, "ws-a", display_name="alpha")
    setup_workspace(deps, "ws-b", display_name="beta")  # no messages/sessions
    seed_message(deps, wid="ws-a", agent="orch", body="hello world")

    resp = client.get("/api/v1/workspaces")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    items = {w["workspace_id"]: w for w in payload["data"]["workspaces"]}
    # BOTH workspaces appear, including the one with no session/message.
    assert set(items) == {"ws-a", "ws-b"}

    a = items["ws-a"]
    for key in (
        "workspace_id", "display_name", "root_realpath", "path_redacted",
        "created_at", "last_seen_at", "is_default", "message_count",
        "event_count", "last_event_at", "open_handoff_count", "presence", "health",
    ):
        assert key in a, f"missing {key}"
    assert a["display_name"] == "alpha"
    assert a["is_default"] is True   # app.state.default_workspace_id == ws-a
    assert items["ws-b"]["is_default"] is False
    assert a["message_count"] == 1
    assert set(a["presence"]) == {"present", "stale", "offline"}
    assert set(a["health"]) == {
        "open_handoffs_unclaimed", "stale_sessions",
        "parked_messages_deadletter", "inbox_backlog_unread",
    }


# --------------------------------------------------------------------------- #
# S2 / AC2 - path gating
# --------------------------------------------------------------------------- #
def test_path_gating_off_then_on(ctx):
    deps, client = ctx
    setup_workspace(deps, "ws-a", root_realpath="/home/me/projects/alpha")

    # Default: expose_workspace_path is OFF -> path redacted.
    off = client.get("/api/v1/workspaces").json()["data"]["workspaces"][0]
    assert off["root_realpath"] is None
    assert off["path_redacted"] is True

    # Flip the live setting on (the route reads it per request).
    deps.config.expose_workspace_path = True
    on = client.get("/api/v1/workspaces").json()["data"]["workspaces"][0]
    assert on["root_realpath"] == "/home/me/projects/alpha"
    assert on["path_redacted"] is False


# --------------------------------------------------------------------------- #
# S5 / AC4 - window validation + empty workspace
# --------------------------------------------------------------------------- #
def test_invalid_window_is_canonical_error(ctx):
    deps, client = ctx
    setup_workspace(deps, "ws-a")
    resp = client.get("/api/v1/workspaces/ws-a/analytics", params={"window": "99h"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_WINDOW"


def test_empty_workspace_returns_zeros(ctx):
    deps, client = ctx
    # Note: even an UNKNOWN workspace id must answer 200 with zeros, not 404.
    resp = client.get("/api/v1/workspaces/ws-unknown/analytics", params={"window": "24h"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["window"] == "24h"
    assert data["bucket_seconds"] == 3600
    assert len(data["buckets"]) == 24
    assert data["summary"]["total_messages"] == 0
    assert data["summary"]["peak_bucket_start"] is None
    assert data["agents"] == []
    assert data["others"] is None


# --------------------------------------------------------------------------- #
# analytics happy path (real tiktoken tokenizer wired in build_app)
# --------------------------------------------------------------------------- #
def test_analytics_basic_shape(ctx):
    deps, client = ctx
    setup_workspace(deps, "ws-a")
    seed_message(deps, wid="ws-a", agent="orch", body="alpha beta gamma")
    seed_message(deps, wid="ws-a", agent="val", body="a longer message body here")

    data = client.get(
        "/api/v1/workspaces/ws-a/analytics", params={"window": "24h"}
    ).json()["data"]

    assert data["bucket_seconds"] == 3600
    assert len(data["buckets"]) == 24
    assert data["summary"]["total_messages"] == 2
    # Real tiktoken: tokens are positive and not equal to char length.
    assert data["summary"]["total_tokens"] > 0
    agents = {a["agent_id"] for a in data["agents"]}
    assert agents == {"orch", "val"}
    # Newest bucket (contains 'now') carries both messages.
    current = data["buckets"][-1]
    assert current["total_count"] == 2


@pytest.mark.parametrize("window,bucket_seconds,n", [("7d", 21600, 28), ("30d", 86400, 30)])
def test_analytics_windows(ctx, window, bucket_seconds, n):
    deps, client = ctx
    setup_workspace(deps, "ws-a")
    data = client.get(
        "/api/v1/workspaces/ws-a/analytics", params={"window": window}
    ).json()["data"]
    assert data["bucket_seconds"] == bucket_seconds
    assert len(data["buckets"]) == n
