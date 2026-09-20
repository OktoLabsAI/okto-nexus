"""REST-surface tests for the harness connector lifecycle (ADR 0004, Phase
3.5 - the ``/api/v1/harness/...`` routes in ``routes.py``).

Integration tests over the REAL application (FastAPI ``TestClient`` + a
migrated SQLite store), mirroring ``tests/test_http_api.py``'s
``serve_env``/``_h`` shape. Reuses the SAME ``FakeConnector`` and connector
factory injection point as ``tests/test_harness_tools.py`` (precedent for
cross-test-module reuse: ``test_capability_catalog.py`` imports
``FakeConnectionFactory`` from ``test_shared_md``), so the two files can
never disagree on what a fake connector actually does.

Every handler in ``routes.py`` calls the SAME ``tools/harness.py``
composition-root/serialisation functions the MCP tools use
(``build_service``, ``build_connector``/``build_connector_factories``,
``session_to_dict``, ``normalize_payload``, ``capabilities_catalog``), so
this file's job is to prove the REST wiring (body parsing, operator gating,
error-code -> HTTP-status mapping, one shared ``HarnessSupervisor`` instance)
rather than re-derive behaviour already covered by
``tests/test_harness_tools.py``.
"""

from __future__ import annotations

import time

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import (  # noqa: E402
    build_app,
    ensure_operator_key,
)
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.application.auth import AgentKeyAuthService  # noqa: E402

from test_harness_tools import _ATTACH_CAPS, _STREAM_CAPS, FakeConnector  # noqa: E402


def _h(key: str) -> dict[str, str]:
    return {"x-api-key": key}


@pytest.fixture
def harness_env(tmp_path):
    """A booted Deps + REST app + operator key, with fake connector
    factories wired in (no real pi/codex/claude binary spawned - see
    ``test_harness_tools.py``'s module docstring for why)."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    home = tmp_path / "nexus_home"
    deps = bootstrap({}, ["--home", str(home)])

    connectors: dict[str, list[FakeConnector]] = {"pi": [], "codex": [], "claude_code": []}

    def _factory(kind: str):
        def factory(*, project_root: str, substrate: str | None, target_pid, **_ignored):
            caps = _STREAM_CAPS
            if kind == "claude_code" and substrate == "attach":
                caps = _ATTACH_CAPS
            conn = FakeConnector(kind=kind, capabilities=caps)
            connectors[kind].append(conn)
            return conn

        return factory

    deps.harness_connector_factories = {
        "pi": _factory("pi"),
        "codex": _factory("codex"),
        "claude_code": _factory("claude_code"),
    }

    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None
    _, operator_key = issued
    app = build_app(deps)
    with TestClient(app) as client:
        # TestClient's fake client is never a real loopback socket connection
        # (request.client.host is not in _LOOPBACK_CLIENTS), so the
        # same-machine keyless-trust convenience never applies here - send
        # the operator key explicitly by default (mirrors
        # test_guardrails.py's guardrail_rest_client fixture). Individual
        # tests override with `headers=` to exercise a DIFFERENT identity.
        client.headers.update({"x-api-key": operator_key})
        yield deps, client, str(project_dir), connectors, operator_key


def _wait_until(predicate, *, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "condition never became true within the timeout"


# --------------------------------------------------------------------------- #
# GET /harness/kinds - open, no auth required
# --------------------------------------------------------------------------- #
def test_harness_kinds_lists_catalog_without_auth(harness_env):
    _deps, client, _root, _connectors, _op = harness_env
    r = client.get("/api/v1/harness/kinds")
    assert r.status_code == 200, r.text
    rows = {(x["kind"], x["substrate"]) for x in r.json()["data"]["harnesses"]}
    assert rows == {("pi", None), ("codex", None), ("claude_code", "stream"), ("claude_code", "attach")}


# --------------------------------------------------------------------------- #
# POST /harness/sessions (open) - operator-gated mutation
# --------------------------------------------------------------------------- #
def test_harness_open_as_operator_registers_agent(harness_env):
    deps, client, root, connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={"agent_id": "pi-rest-1", "kind": "pi", "project_root": root},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "RUNNING"
    assert data["owning_agent_id"] == "pi-rest-1"
    assert len(connectors["pi"]) == 1

    with deps.connection_factory.unit_of_work(write=False) as uow:
        agent = deps.repos.agents.get(uow, "pi-rest-1")
    assert agent is not None


def test_harness_open_rejects_unknown_kind(harness_env):
    _deps, client, root, _connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={"agent_id": "x", "kind": "not-a-kind", "project_root": root},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_harness_open_claude_code_attach_requires_target_pid(harness_env):
    _deps, client, root, _connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={
            "agent_id": "cc",
            "kind": "claude_code",
            "project_root": root,
            "substrate": "attach",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_harness_open_default_backend_is_ambient_and_visible_in_response(harness_env):
    """H-1 (EV-SYS-002), REST mirror: omitting backend keeps today's
    ambient-inherit default, but the response must say so explicitly."""
    _deps, client, root, _connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={"agent_id": "pi-rest-backend-0", "kind": "pi", "project_root": root},
    )
    assert r.status_code == 200, r.text
    backend_info = r.json()["data"]["backend"]
    assert backend_info["explicit"] is False
    assert backend_info["applied"] == {}
    assert "ambient" in backend_info["note"]


def test_harness_open_backend_override_is_honored_over_rest(harness_env):
    """H-1 (EV-SYS-002): the operator can say which provider/model this
    session uses over the REST mirror too - parity with the MCP tool is a
    hard gate for this surface."""
    _deps, client, root, connectors, _op = harness_env
    backend = {"provider": "zai", "model": "glm-5.3"}
    r = client.post(
        "/api/v1/harness/sessions",
        json={
            "agent_id": "pi-rest-backend-1",
            "kind": "pi",
            "project_root": root,
            "backend": backend,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["backend"]["explicit"] is True
    assert data["backend"]["applied"] == backend
    assert len(connectors["pi"]) == 1


def test_harness_open_rejects_backend_field_unsupported_for_kind_over_rest(harness_env):
    _deps, client, root, connectors, _op = harness_env
    r = client.post(
        "/api/v1/harness/sessions",
        json={
            "agent_id": "codex-rest-backend",
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
            "agent_id": "cc-rest-backend",
            "kind": "claude_code",
            "project_root": root,
            "substrate": "attach",
            "target_pid": 4242,
            "backend": {"env": {"X": "1"}},
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
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
        json={"agent_id": "pi-rest-2", "kind": "pi", "project_root": root},
    ).json()["data"]
    session_id = opened["session_id"]
    conn = connectors["pi"][0]

    r = client.post(
        f"/api/v1/harness/sessions/{session_id}/send", json={"payload": {"text": "hi"}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verb"] == "send_turn"

    r = client.post(
        f"/api/v1/harness/sessions/{session_id}/steer",
        json={"payload": {"text": "actually wait"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verb"] == "steer"

    r = client.post(f"/api/v1/harness/sessions/{session_id}/interrupt", json={})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["verb"] == "interrupt"

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
    assert r.json()["data"]["status"] == "ENDED"
    assert conn.close_called is True

    after = client.get(f"/api/v1/harness/sessions/{session_id}").json()["data"]
    assert after["live"] is False and after["status"] == "ENDED"

    second_close = client.post(f"/api/v1/harness/sessions/{session_id}/close")
    assert second_close.status_code == 404
    assert second_close.json()["error"]["code"] == "NOT_FOUND"


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

    from okto_nexus.adapters.inbound.mcp.tools import harness as harness_tools

    class _Capture:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def deco(fn):
                self.tools[fn.__name__] = fn
                return fn

            return deco

    mcp_server = _Capture()
    harness_tools.register(mcp_server, deps)

    import asyncio

    opened = asyncio.run(
        mcp_server.tools["harness_open"](
            agent_id="pi-shared", kind="pi", project_root=root
        )
    )
    assert opened["ok"], opened
    session_id = opened["data"]["session_id"]

    # Visible over REST without a second open.
    r = client.get(f"/api/v1/harness/sessions/{session_id}")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["live"] is True

    # Controllable over REST too.
    r = client.post(f"/api/v1/harness/sessions/{session_id}/close")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "ENDED"
