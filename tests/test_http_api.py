"""HTTP serve surface: auth gate, agents CRUD, graph, events, SSE (spec S1).

Integration tests over the REAL application (FastAPI TestClient + migrated
SQLite store). Maps to scenarios TS1-TS6 of the backend spec:

* uniform 401 with zero side effects (TS2 / AC2)
* agent creation with single plaintext exposure + hash-only storage (TS3/AC3)
* regenerate invalidating the previous key immediately (TS4 / AC4)
* graph snapshot with derived presence + in-flight lanes (TS5 / AC5)
* SSE delivery and Last-Event-ID resume without loss/duplication (TS6 / AC6)
"""

from __future__ import annotations

import json
import threading

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.application.auth import AgentKeyAuthService  # noqa: E402


@pytest.fixture
def serve_env(tmp_path):
    """A booted Deps + app + operator key over a temp store."""
    home = tmp_path / "nexus_home"
    deps = bootstrap({}, ["--home", str(home)])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None
    _, operator_key = issued
    app = build_app(deps)
    app.state.sse_poll_seconds = 0.05  # keep SSE tests fast
    app.state.sse_ping_seconds = 0.2
    with TestClient(app) as client:
        yield deps, client, operator_key


def _h(key: str) -> dict[str, str]:
    return {"x-api-key": key}


def _table_counts(deps) -> dict[str, int]:
    tables = (
        "agents",
        "sessions",
        "events",
        "messages",
        "message_deliveries",
        "handoffs",
    )
    with deps.connection_factory.unit_of_work() as uow:
        return {
            t: uow.connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in tables
        }


# --------------------------------------------------------------------------- #
# Same-machine trust (operator convenience): loopback clients reach the
# REST/dashboard without a key; /mcp keeps requiring one on EVERY transport.
# The TestClient's client host is "testclient" (not loopback), so every other
# test in this file still exercises the key-gated path.
# --------------------------------------------------------------------------- #
def test_loopback_opens_rest_but_never_mcp(tmp_path):
    home = tmp_path / "nexus_home"
    deps = bootstrap({}, ["--home", str(home)])
    app = build_app(deps)
    assert app.state.local_open is True  # the local-first default

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        # REST without any key: allowed for the local operator.
        assert client.get("/api/v1/graph").status_code == 200
        assert client.get("/api/v1/agents").status_code == 200
        # /mcp: an MCP connection IS an agent identity - key required even
        # from loopback (D5).
        response = client.post("/mcp", json={})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_FAILED"

        # Bound beyond loopback (serve sets local_open=False): key required.
        app.state.local_open = False
        assert client.get("/api/v1/graph").status_code == 401


def test_non_loopback_client_requires_key_even_when_local_open(tmp_path):
    home = tmp_path / "nexus_home"
    deps = bootstrap({}, ["--home", str(home)])
    app = build_app(deps)  # local_open=True

    with TestClient(app, client=("192.168.0.50", 50000)) as client:
        assert client.get("/api/v1/graph").status_code == 401


# --------------------------------------------------------------------------- #
# Auth gate (AC2)
# --------------------------------------------------------------------------- #
def test_public_paths_do_not_require_a_key(serve_env):
    _, client, _ = serve_env
    assert client.get("/healthz").status_code == 200
    assert client.get("/").status_code == 200
    assert client.get("/api/v1/info").status_code == 200


def test_missing_unknown_and_revoked_keys_are_uniform_401(serve_env):
    deps, client, operator_key = serve_env

    # Create a second agent, then deactivate it.
    created = client.post(
        "/api/v1/agents",
        json={"agent_id": "revoked-bot"},
        headers=_h(operator_key),
    ).json()["data"]
    client.patch(
        "/api/v1/agents/revoked-bot",
        json={"is_active": False},
        headers=_h(operator_key),
    )

    before = _table_counts(deps)
    for headers in (
        {},  # missing
        _h("nxs_" + "0" * 48),  # unknown
        _h(created["api_key"]),  # revoked agent's key
        {"authorization": "Bearer total-garbage"},  # malformed
    ):
        response = client.get("/api/v1/graph", headers=headers)
        assert response.status_code == 401
        body = response.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "AUTH_FAILED"
    # Zero side effects: rejected requests wrote nothing (AC2).
    assert _table_counts(deps) == before


def test_key_accepted_via_query_header_and_bearer(serve_env):
    _, client, operator_key = serve_env
    assert client.get(f"/api/v1/graph?api_key={operator_key}").status_code == 200
    assert client.get("/api/v1/graph", headers=_h(operator_key)).status_code == 200
    assert (
        client.get(
            "/api/v1/graph", headers={"authorization": f"Bearer {operator_key}"}
        ).status_code
        == 200
    )


# --------------------------------------------------------------------------- #
# Agent management (AC3 / AC4)
# --------------------------------------------------------------------------- #
def test_create_agent_exposes_plaintext_once_and_stores_hash_only(serve_env):
    deps, client, operator_key = serve_env
    response = client.post(
        "/api/v1/agents",
        json={"agent_id": "researcher", "role": "analyst", "capabilities": ["ocr"]},
        headers=_h(operator_key),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    plaintext = data["api_key"]
    assert plaintext.startswith("nxs_")

    # No later surface carries the plaintext.
    listing = client.get("/api/v1/agents", headers=_h(operator_key)).json()["data"]
    detail = client.get("/api/v1/agents/researcher", headers=_h(operator_key)).json()[
        "data"
    ]
    assert plaintext not in json.dumps(listing)
    assert plaintext not in json.dumps(detail)
    assert detail["has_key"] is True

    # Storage holds the hash, never the plaintext.
    with deps.connection_factory.unit_of_work() as uow:
        row = uow.connection.execute(
            "SELECT api_key_hash FROM agents WHERE agent_id = 'researcher'"
        ).fetchone()
    assert row["api_key_hash"] is not None and row["api_key_hash"] != plaintext

    # The new key authenticates; duplicate creation conflicts.
    assert client.get("/api/v1/graph", headers=_h(plaintext)).status_code == 200
    duplicate = client.post(
        "/api/v1/agents", json={"agent_id": "researcher"}, headers=_h(operator_key)
    )
    assert duplicate.status_code == 409


def test_regenerate_key_invalidates_previous_immediately(serve_env):
    _, client, operator_key = serve_env
    first = client.post(
        "/api/v1/agents", json={"agent_id": "rotator"}, headers=_h(operator_key)
    ).json()["data"]["api_key"]
    assert client.get("/api/v1/graph", headers=_h(first)).status_code == 200

    second = client.post(
        "/api/v1/agents/rotator/regenerate-key", headers=_h(operator_key)
    ).json()["data"]["api_key"]

    assert client.get("/api/v1/graph", headers=_h(first)).status_code == 401
    assert client.get("/api/v1/graph", headers=_h(second)).status_code == 200
    assert first != second


def test_delete_agent_removes_and_404s_afterwards(serve_env):
    _, client, operator_key = serve_env
    key = client.post(
        "/api/v1/agents", json={"agent_id": "ephemeral"}, headers=_h(operator_key)
    ).json()["data"]["api_key"]
    assert (
        client.delete("/api/v1/agents/ephemeral", headers=_h(operator_key)).status_code
        == 200
    )
    assert client.get("/api/v1/graph", headers=_h(key)).status_code == 401
    assert (
        client.get("/api/v1/agents/ephemeral", headers=_h(operator_key)).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# Graph snapshot (AC5)
# --------------------------------------------------------------------------- #
def test_graph_reflects_presence_and_in_flight(serve_env):
    deps, client, operator_key = serve_env
    repos = deps.repos
    with deps.connection_factory.unit_of_work() as uow:
        ws = "w" * 64
        repos.workspaces.upsert(uow, workspace_id=ws)
        for agent_id in ("alpha", "bravo", "charlie"):
            repos.agents.upsert(uow, agent_id=agent_id)
        # alpha: fresh heartbeat -> present. bravo: stale (5 min old).
        repos.sessions.create(
            uow, session_id="s-alpha", agent_id="alpha", workspace_id=ws,
            status="active",
        )
        repos.sessions.create(
            uow, session_id="s-bravo", agent_id="bravo", workspace_id=ws,
            status="active",
        )
        import datetime

        old = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=300)
        ).isoformat().replace("+00:00", "Z")
        uow.connection.execute(
            "UPDATE sessions SET last_heartbeat_at = ? WHERE session_id = 's-bravo'",
            (old,),
        )
        # One in-flight (unread) message alpha -> bravo.
        repos.messages.create(
            uow,
            message_id="m1",
            workspace_id=ws,
            from_agent_id="alpha",
            body="ping",
        )
        repos.deliveries.create(
            uow,
            delivery_id="d1",
            message_id="m1",
            recipient_agent_id="bravo",
            status="unread",
        )

    data = client.get(
        f"/api/v1/graph?workspace={'w' * 64}", headers=_h(operator_key)
    ).json()["data"]

    presence = {n["agent_id"]: n["presence"] for n in data["nodes"]}
    assert presence["alpha"] == "present"
    assert presence["bravo"] == "stale"
    assert presence["charlie"] == "offline"

    edges = data["edges"]["messages"]
    assert len(edges) == 1
    edge = edges[0]
    assert (edge["from"], edge["to"], edge["count"]) == ("alpha", "bravo", 1)
    assert edge["in_flight"]["unread"] == 1

    bravo = next(n for n in data["nodes"] if n["agent_id"] == "bravo")
    assert bravo["inbox"]["unread"] == 1


# --------------------------------------------------------------------------- #
# Admin reset (Settings > wipe store)
# --------------------------------------------------------------------------- #
def test_admin_reset_wipes_data_but_keeps_agents(serve_env):
    deps, client, operator_key = serve_env
    ws = "r" * 64
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=ws)
        deps.repos.agents.upsert(uow, agent_id="survivor")
        deps.repos.sessions.create(
            uow, session_id="s-reset", agent_id="survivor", workspace_id=ws,
            status="active",
        )
        deps.repos.messages.create(
            uow, message_id="m-reset", workspace_id=ws, from_agent_id="survivor",
            body="to be wiped",
        )
        deps.repos.deliveries.create(
            uow, delivery_id="d-reset", message_id="m-reset",
            recipient_agent_id="survivor", status="unread",
        )
    deps.event_emitter  # noqa: B018 - events table already has rows from setup

    response = client.post(
        "/api/v1/admin/reset", headers=_h(operator_key)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["kept_agents"] is True
    assert data["deleted"]["messages"] >= 1

    with deps.connection_factory.unit_of_work() as uow:
        for table in ("messages", "message_deliveries", "sessions", "workspaces"):
            count = uow.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, table
        agents = uow.connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        assert agents >= 2  # operator + survivor preserved

    # The operator key still authenticates after the wipe (keys preserved).
    assert client.get("/api/v1/graph", headers=_h(operator_key)).status_code == 200


# --------------------------------------------------------------------------- #
# Events + SSE (AC6)
# --------------------------------------------------------------------------- #
def _emit_event(deps, ws: str, type_: str) -> int:
    with deps.connection_factory.unit_of_work() as uow:
        return deps.event_emitter.emit(
            uow, workspace_id=ws, stream="workspace", type=type_
        )


def test_events_endpoint_pages_by_cursor(serve_env):
    deps, client, operator_key = serve_env
    ws = "e" * 64
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=ws)
    first = _emit_event(deps, ws, "demo.one")
    second = _emit_event(deps, ws, "demo.two")

    page = client.get(
        f"/api/v1/events?after={first}", headers=_h(operator_key)
    ).json()["data"]
    ids = [item["event_id"] for item in page["items"]]
    assert ids == [second]
    assert page["next_cursor"] == second


def test_sse_streams_new_events_and_resumes_after_cursor(tmp_path):
    """True e2e (TS6): a REAL uvicorn server on a free port.

    The in-process TestClient buffers/deadlocks on never-ending streaming
    responses, so the SSE path is exercised the way production consumes it:
    over a socket, with a plain httpx streaming client.
    """
    import socket
    import time

    import httpx
    import uvicorn

    home = tmp_path / "nexus_home"
    deps = bootstrap({}, ["--home", str(home)])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None
    _, operator_key = issued

    app = build_app(deps)
    app.state.sse_poll_seconds = 0.05
    app.state.sse_ping_seconds = 60.0

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn failed to start"
        time.sleep(0.05)

    try:
        ws = "s" * 64
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.workspaces.upsert(uow, workspace_id=ws)
        e1 = _emit_event(deps, ws, "sse.first")

        base = f"http://127.0.0.1:{port}"
        received: list[dict] = []
        first_latency: float | None = None

        timer = threading.Timer(
            0.15,
            lambda: (_emit_event(deps, ws, "sse.second"), _emit_event(deps, ws, "sse.third")),
        )
        with httpx.Client(timeout=10.0) as client:
            with client.stream(
                "GET",
                f"{base}/api/v1/stream",
                headers={**_h(operator_key), "last-event-id": str(e1)},
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith(
                    "text/event-stream"
                )
                opened = time.monotonic()
                timer.start()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        if first_latency is None:
                            first_latency = time.monotonic() - opened
                        received.append(json.loads(line[6:]))
                    if len(received) >= 2:
                        break
        timer.cancel()

        types = [event["type"] for event in received]
        ids = [event["event_id"] for event in received]
        # Resume semantics: e1 (== cursor) is NOT re-sent; both later events
        # arrive in order, exactly once, well inside the 2s budget (AC6).
        assert types == ["sse.second", "sse.third"]
        assert ids == sorted(ids) and e1 not in ids
        assert first_latency is not None and first_latency < 2.0
    finally:
        server.should_exit = True
        thread.join(timeout=10)
