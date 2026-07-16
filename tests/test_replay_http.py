"""TC3 - REST export endpoint tests (spec c7c1f834, TS5 + TS6 + TS7).

GET /api/v1/workspaces/{id}/events/export over TestClient: the two fail-closed
gates (feature_replay opt-in -> 422 before any byte/DB access; operator-only ->
403 for a common agent) and the happy path (200 NDJSON stream, filters recortam,
Content-Disposition + media_type).
"""

from __future__ import annotations

import json

import pytest

from okto_nexus.testing import build_hub, pin_clock

pytestmark = pytest.mark.replay

_TRACE = "trace-http-001"


def _ok(env):
    assert env["ok"] is True, env
    return env["data"]


def _direct(agent):
    return {"strategy": "direct", "agent_id": agent}


def _seed(hub):
    tools = hub.tools
    clock = pin_clock(hub.deps, 1_800_000_000.0)
    project = hub.home / "project"
    project.mkdir(exist_ok=True)
    root = str(project)
    wid = _ok(tools["workspace_resolve"](project_root=root))["workspace_id"]
    for aid, role in (("alpha", "builder"), ("beta", "executor")):
        _ok(tools["agent_register"](agent_id=aid, role=role))
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="m1",
            body="x",
            target=_direct("beta"),
        )
    )
    clock.advance(5)
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="traced",
            body="y",
            target=_direct("beta"),
            trace_id=_TRACE,
        )
    )
    clock.advance(5)
    h = _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload="job",
        )
    )["handoff_id"]
    clock.advance(10)
    _ok(tools["handoff_claim"](project_root=root, handoff_id=h, agent_id="beta"))
    clock.set(1_800_001_000.0)
    return root, wid


def _app(hub):
    from okto_nexus.adapters.inbound.http.app import build_app

    return build_app(hub.deps)


def _operator_key(hub):
    from okto_nexus.adapters.inbound.http.app import ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService

    auth = AgentKeyAuthService(hub.deps.repos.agents, hub.deps.clock)
    issued = ensure_operator_key(hub.deps, auth)
    assert issued is not None
    return issued[1]


def _issue_key(hub, agent_id):
    from okto_nexus.application.auth import AgentKeyAuthService

    auth = AgentKeyAuthService(hub.deps.repos.agents, hub.deps.clock)
    with hub.deps.connection_factory.unit_of_work() as uow:
        return auth.issue_key(uow, agent_id=agent_id)


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


# --------------------------------------------------------------------------- #
# TS5 - feature_replay OFF -> 422 before streaming (fail-closed, BR1)
# --------------------------------------------------------------------------- #
def test_ts5_export_disabled_returns_422_citing_flag() -> None:
    hub = build_hub()  # feature_replay OFF (default)
    _, wid = _seed(hub)
    operator_key = _operator_key(hub)  # auth passes the middleware; the FLAG gate
    client = _client(_app(hub))  # then fires 422 in the handler, before operator check

    resp = client.get(
        f"/api/v1/workspaces/{wid}/events/export", headers={"x-api-key": operator_key}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "feature_replay" in body["error"]["message"]
    # not a single NDJSON byte leaked: the body is the JSON error envelope
    assert "kind" not in body and '"kind":"manifest"' not in resp.text


# --------------------------------------------------------------------------- #
# TS6 - operator gate: common agent 403, operator 200 (BR2)
# --------------------------------------------------------------------------- #
def test_ts6_non_operator_forbidden_operator_streams() -> None:
    hub = build_hub({"OKTO_NEXUS_FEATURE_REPLAY": "true"})
    _, wid = _seed(hub)
    operator_key = _operator_key(hub)  # FIRST (no keys yet) so it is issued
    alpha_key = _issue_key(hub, "alpha")
    client = _client(_app(hub))

    url = f"/api/v1/workspaces/{wid}/events/export"

    denied = client.get(url, headers={"x-api-key": alpha_key})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"

    allowed = client.get(url, headers={"x-api-key": operator_key})
    assert allowed.status_code == 200, allowed.text
    assert allowed.headers["content-type"].startswith("application/x-ndjson")
    lines = allowed.text.splitlines()
    assert json.loads(lines[0])["kind"] == "manifest"
    assert len(lines) >= 2  # manifest + at least one event


# --------------------------------------------------------------------------- #
# TS7 - filters recortam + Content-Disposition + media_type
# --------------------------------------------------------------------------- #
def test_ts7_filters_and_download_headers() -> None:
    hub = build_hub(
        {"OKTO_NEXUS_FEATURE_REPLAY": "true", "OKTO_NEXUS_FEATURE_TRACE": "true"}
    )
    root, wid = _seed(hub)
    operator_key = _operator_key(hub)
    client = _client(_app(hub))
    url = f"/api/v1/workspaces/{wid}/events/export"
    hdr = {"x-api-key": operator_key}

    # stream filter recorta to handoff-only
    resp = client.get(url, params={"stream": "handoff"}, headers=hdr)
    assert resp.status_code == 200
    manifest, *events = resp.text.splitlines()
    manifest = json.loads(manifest)
    assert manifest["filters"]["stream"] == "handoff"
    events = [json.loads(e) for e in events]
    assert events and all(e["stream"] == "handoff" for e in events)

    # download affordances
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    cd = resp.headers["content-disposition"]
    assert cd.startswith("attachment;") and cd.endswith('.ndjson"')
    assert wid[:8] in cd

    # trace filter (json_extract) recorta to exactly the traced message
    traced = client.get(url, params={"trace": _TRACE}, headers=hdr)
    assert traced.status_code == 200
    t_manifest, *t_events = traced.text.splitlines()
    assert json.loads(t_manifest)["filters"]["trace_id"] == _TRACE
    t_events = [json.loads(e) for e in t_events]
    assert len(t_events) == 1 and t_events[0]["payload"].get("trace_id") == _TRACE

    # since is exclusive
    all_ids = [
        json.loads(e)["event_id"]
        for e in client.get(url, headers=hdr).text.splitlines()[1:]
    ]
    pivot = all_ids[0]
    after = client.get(url, params={"since_event_id": pivot}, headers=hdr)
    after_ids = [json.loads(e)["event_id"] for e in after.text.splitlines()[1:]]
    assert all(i > pivot for i in after_ids)
