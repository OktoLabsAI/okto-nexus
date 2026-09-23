"""REST lifecycle regressions over a real socket, production auth and MCP mount.

Uses canonical fixture agents and approved profiles. Only external peers are
synthetic; runtime ownership, journaling and application services are real.
"""

from __future__ import annotations

import time

import pytest

from test_harness_tools import FakeConnector
from test_pr34_remediation import runtime as runtime_fixture, tool

from test_runtime_commands import wait_close_result

runtime = runtime_fixture


def _h(key: str) -> dict[str, str]:
    return {"x-api-key": key}


@pytest.fixture
def harness_env(runtime):
    # Use the actual socket/MCP/REST owner fixture, approved profiles and the
    # existing canonical worker. Only external peers are synthetic.
    deps, client, root, _peers, operator_key, _caller = runtime
    connectors: dict[str, list[FakeConnector]] = {"pi": [], "codex": [], "claude_code": []}
    originals = deps.harness_connector_factories.copy()

    def wrap(kind):
        def build(**kwargs):
            peer = originals[kind](**kwargs)
            connectors[kind].append(peer)
            return peer
        return build

    deps.harness_connector_factories.update({kind: wrap(kind) for kind in originals})
    client.headers.update({"x-api-key": operator_key})
    yield deps, client, root, connectors, operator_key


def _wait_until(predicate, *, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "condition never became true within the timeout"


# --------------------------------------------------------------------------- #
# GET /harness/kinds - authenticated runtime catalog
# --------------------------------------------------------------------------- #
def test_harness_kinds_lists_catalog_for_authorized_operator(harness_env):
    _deps, client, _root, _connectors, _op = harness_env
    r = client.get("/api/v1/harness/kinds")
    assert r.status_code == 200, r.text
    rows = {(x["kind"], x["substrate"]) for x in r.json()["data"]["harnesses"]}
    assert rows == {("pi", None), ("codex", None), ("claude_code", "stream"), ("claude_code", "attach")}


# --------------------------------------------------------------------------- #
# POST /harness/sessions (open) - operator-gated mutation
# --------------------------------------------------------------------------- #
def test_harness_open_as_operator_preserves_agent(harness_env):
    deps, client, root, connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={"agent_id": "worker", "kind": "pi", "project_root": root},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "RUNNING"
    assert data["owning_agent_id"] == "worker"
    assert len(connectors["pi"]) == 1

    with deps.connection_factory.unit_of_work(write=False) as uow:
        agent = deps.repos.agents.get(uow, "worker")
    assert agent is not None and agent.role == "reviewer"
    assert agent.capabilities == {"review": True} and agent.metadata == {"keep": "profile"}


def test_harness_open_rejects_unknown_kind(harness_env):
    _deps, client, root, _connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={"agent_id": "worker", "kind": "not-a-kind", "project_root": root},
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert "endpoint" in r.json()["error"]["message"]


def test_harness_open_claude_code_attach_requires_target_pid(harness_env):
    _deps, client, root, _connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={
            "agent_id": "worker",
            "kind": "claude_code",
            "project_root": root,
            "substrate": "attach",
        },
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_harness_open_default_profile_is_isolated_and_visible_in_response(harness_env):
    """Approved profile metadata is explicit and ambient inheritance defaults off."""
    _deps, client, root, _connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={"agent_id": "worker", "kind": "pi", "project_root": root},
    )
    assert r.status_code == 200, r.text
    backend_info = r.json()["data"]["backend"]
    assert backend_info == {"profile_id": "profile-pi", "inherit_ambient": False, "revision": 1}


def test_harness_open_per_call_backend_override_is_rejected(harness_env):
    """Backend changes require an approved profile, even for the operator."""
    _deps, client, root, connectors, _op = harness_env
    backend = {"provider": "zai", "model": "glm-5.3"}
    r = client.post(
        "/api/v1/harness/sessions",
        json={
            "agent_id": "worker",
            "kind": "pi",
            "project_root": root,
            "backend": backend,
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not connectors["pi"]


def test_harness_open_rejects_backend_field_unsupported_for_kind_over_rest(harness_env):
    _deps, client, root, connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={
            "agent_id": "worker",
            "kind": "codex",
            "project_root": root,
            "backend": {"provider": "zai"},
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert connectors["codex"] == []


def test_harness_open_rejects_backend_for_claude_code_attach_substrate_over_rest(harness_env):
    _deps, client, root, connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={
            "agent_id": "worker",
            "kind": "claude_code",
            "project_root": root,
            "substrate": "attach",
            "target_pid": 4242,
            "backend": {"env": {"X": "1"}},
        },
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"
    assert connectors["claude_code"] == []


def test_harness_open_as_non_operator_is_forbidden(harness_env):
    deps, client, root, _connectors, operator_key = harness_env
    created = client.post(
        "/api/v1/agents", json={"agent_id": "peon"}, headers=_h(operator_key)
    ).json()["data"]
    peon = _h(created["api_key"])

    r = client.post(
        "/api/v1/harness/sessions",
        json={"agent_id": "pi-x", "kind": "pi", "project_root": root},
        headers=peon,
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"


# --------------------------------------------------------------------------- #
# send / steer / interrupt / close / get / events
# --------------------------------------------------------------------------- #
def test_harness_full_lifecycle_through_rest(harness_env):
    deps, client, root, connectors, _op = harness_env
    opened = client.post(
        "/api/v1/harness/sessions",
        json={"agent_id": "worker", "kind": "pi", "project_root": root},
    ).json()["data"]
    session_id = opened["session_id"]
    conn = connectors["pi"][0]

    r = client.post(
        f"/api/v1/harness/sessions/{session_id}/send", json={"payload": {"text": "hi"}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verb"] == "send_turn"
    _wait_until(lambda: len(conn.sent) == 1)

    r = client.post(
        f"/api/v1/harness/sessions/{session_id}/steer",
        json={"payload": {"text": "actually wait"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verb"] == "steer"

    r = client.post(f"/api/v1/harness/sessions/{session_id}/interrupt", json={})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verb"] == "interrupt"

    _wait_until(lambda: len(conn.sent) == 3)
    assert [c.verb for c in conn.sent] == ["send_turn", "steer", "interrupt"]

    conn.push_event(kind="turn_completed", native_event="agent_settled")

    def _events_seen() -> bool:
        resp = client.get(f"/api/v1/harness/sessions/{session_id}/events")
        return resp.json()["data"]["count"] >= 1

    _wait_until(_events_seen)

    ev = client.get(f"/api/v1/harness/sessions/{session_id}/events").json()["data"]
    assert ev["events"][0]["native_event"] == "agent_settled"

    live = client.get(f"/api/v1/harness/sessions/{session_id}").json()["data"]
    assert live["live"] is True and live["status"] == "RUNNING"

    r = client.post(f"/api/v1/harness/sessions/{session_id}/close")
    assert r.status_code == 200, r.text
    assert wait_close_result(client, _op, r)["lifecycle_state"] == "detached"
    assert conn.close_called is True

    after = client.get(f"/api/v1/harness/sessions/{session_id}").json()["data"]
    assert after["live"] is False and after["lifecycle_state"] == "detached"

    second_close = client.post(f"/api/v1/harness/sessions/{session_id}/close")
    assert second_close.status_code == 200
    assert wait_close_result(client, _op, second_close)["lifecycle_state"] == "detached"


def test_harness_get_unknown_session_is_404(harness_env):
    _deps, client, _root, _connectors, _op = harness_env
    r = client.get("/api/v1/harness/sessions/hsess_never_opened")
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_harness_send_against_unknown_session_is_404(harness_env):
    _deps, client, _root, _connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions/hsess_nope/send", json={"payload": {"text": "hi"}}
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# MCP <-> REST: one shared supervisor instance (D1: in-process with serve)
# --------------------------------------------------------------------------- #
def test_mcp_and_rest_surfaces_share_one_live_registry(harness_env, tmp_path):
    """A session opened over ONE surface must be visible/controllable over
    the OTHER - both are wired to the SAME process-wide HarnessSupervisor
    (``tools/harness.py``'s ``build_service`` cache on ``deps``), never two
    independent registries."""
    deps, client, root, connectors, _op = harness_env

    opened = tool(client, _op, "harness_open", {
        "agent_id": "worker", "kind": "pi", "project_root": root,
        "idempotency_key": "shared-rest-mcp-fixture"})
    assert opened["ok"], opened
    session_id = opened["data"]["session_id"]

    # Visible over REST without a second open.
    r = client.get(f"/api/v1/harness/sessions/{session_id}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["live"] is True

    # Controllable over REST too.
    r = client.post(f"/api/v1/harness/sessions/{session_id}/close")
    assert r.status_code == 200, r.text
    assert wait_close_result(client, _op, r)["lifecycle_state"] == "detached"
