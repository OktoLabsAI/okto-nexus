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




def test_harness_open_claude_code_attach_respects_explicit_disable(harness_env):
    _deps, client, root, _connectors, _op = harness_env
    _deps.config.feature_harness_attach = False
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
