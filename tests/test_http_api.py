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
from datetime import datetime, timedelta, timezone

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.application.auth import AgentKeyAuthService  # noqa: E402
from okto_nexus.domain.ids import resolve_realpath, resolve_workspace_id  # noqa: E402


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


def test_loopback_trust_refuses_cross_origin_and_dns_rebinding(tmp_path):
    """The keyless same-machine opening must not be ridable by a BROWSER: a
    cross-site fetch (foreign Origin) or a DNS-rebound Host is refused 403,
    while curl/agents (no Origin, no Fetch-Metadata) and the real dashboard
    (loopback Origin + Host) still pass."""
    home = tmp_path / "nexus_home"
    deps = bootstrap({}, ["--home", str(home)])
    app = build_app(deps)

    with TestClient(app, client=("127.0.0.1", 50010)) as client:
        # Non-browser same-machine caller (no Origin / no Fetch-Metadata): trusted.
        assert client.get("/api/v1/graph").status_code == 200
        # The real dashboard: loopback Origin + Host + Fetch-Metadata -> trusted.
        dashboard = {
            "origin": "http://127.0.0.1:8202",
            "host": "127.0.0.1:8202",
            "sec-fetch-site": "same-origin",
        }
        assert client.get("/api/v1/graph", headers=dashboard).status_code == 200
        # Dev proxy origin (vite :5202) is loopback too -> trusted.
        dev = {"origin": "http://localhost:5202"}
        assert client.get("/api/v1/graph", headers=dev).status_code == 200

        # Cross-site CSRF: a foreign Origin on the loopback socket -> 403.
        evil = client.get("/api/v1/graph", headers={"origin": "https://evil.example"})
        assert evil.status_code == 403
        assert evil.json()["error"]["code"] == "CROSS_ORIGIN_BLOCKED"
        # A state-changing CSRF write is refused in the middleware, before the
        # handler runs (no policy is ever created).
        wrote = client.post(
            "/api/v1/policies",
            json={"name": "x"},
            headers={"origin": "https://evil.example"},
        )
        assert wrote.status_code == 403
        assert wrote.json()["error"]["code"] == "CROSS_ORIGIN_BLOCKED"

        # Read-only DNS-rebinding: a browser (Sec-Fetch-Site) with the
        # attacker's domain as Host but NO Origin (same-origin GET) -> 403.
        rebound = client.get(
            "/api/v1/graph",
            headers={"sec-fetch-site": "same-origin", "host": "evil.example"},
        )
        assert rebound.status_code == 403
        assert rebound.json()["error"]["code"] == "CROSS_ORIGIN_BLOCKED"
        # A non-browser caller (no Fetch-Metadata) with an odd Host is NOT a
        # rebinding vector - curl on the box can set any Host and is trusted.
        assert (
            client.get("/api/v1/graph", headers={"host": "evil.example"}).status_code
            == 200
        )


def test_destructive_surfaces_are_operator_only_off_loopback(serve_env):
    """Every destructive / privileged REST surface requires the operator
    identity: a valid but NON-operator key is refused 403 PERMISSION_DENIED
    (previously any authenticated key passed). Covers config/admin, the legacy
    governance CRUD, agent+key management (incl. the operator-takeover via
    regenerate-key), the tag/capability/preset catalogs and the admin
    session/handoff force-actions."""
    _, client, operator_key = serve_env
    created = client.post(
        "/api/v1/agents",
        json={"agent_id": "peon"},
        headers=_h(operator_key),
    ).json()["data"]
    peon = _h(created["api_key"])

    forbidden = (
        # config / admin
        client.patch("/api/v1/settings", json={}, headers=peon),
        client.post("/api/v1/settings/reset", headers=peon),
        client.post("/api/v1/admin/reset", headers=peon),
        client.post("/api/v1/admin/prune", headers=peon),
        # legacy governance CRUD
        client.get("/api/v1/governance/policies", headers=peon),
        client.post("/api/v1/governance/policies", json={}, headers=peon),
        client.patch("/api/v1/governance/policies/nope", json={}, headers=peon),
        client.delete("/api/v1/governance/policies/nope", headers=peon),
        # agent + key management (regenerate-key was operator-account-takeover)
        client.post("/api/v1/agents", json={"agent_id": "intruder"}, headers=peon),
        client.patch("/api/v1/agents/operator", json={}, headers=peon),
        client.delete("/api/v1/agents/operator", headers=peon),
        client.post("/api/v1/agents/operator/regenerate-key", headers=peon),
        # tag / capability / preset catalogs (documented operator-only)
        client.post("/api/v1/tags", json={"key": "team"}, headers=peon),
        client.delete("/api/v1/tags/team", headers=peon),
        client.post("/api/v1/capabilities", json={"name": "ocr"}, headers=peon),
        client.delete("/api/v1/capabilities/ocr", headers=peon),
        client.delete("/api/v1/presets/prs_nope", headers=peon),
        # admin force-actions (the agent path is the MCP verb, not this REST)
        client.post("/api/v1/sessions/sess_nope/close", headers=peon),
        client.post("/api/v1/handoffs/ho_nope/cancel?workspace=w", headers=peon),
        client.post(
            "/api/v1/meta-harness/send",
            json={
                "workspace": "w",
                "kind": "message",
                "audience": "broadcast",
                "body": "intrusion",
            },
            headers=peon,
        ),
    )
    for response in forbidden:
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    # CRITICAL regression: the refused regenerate-key above did NOT rotate the
    # operator's key, so the operator credential still authenticates (no
    # account takeover), and the operator still passes every gate.
    assert client.get("/api/v1/agents", headers=_h(operator_key)).status_code == 200
    assert (
        client.get("/api/v1/governance/policies", headers=_h(operator_key)).status_code
        == 200
    )


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
    # Capabilities are fail-closed: the vocabulary must exist in the catalog
    # before an agent may announce it (capability-catalog feature).
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.capability_catalog.ensure(uow, name="ocr")
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


def test_delete_agent_with_sessions_and_deliveries_cascades(serve_env):
    """Deleting an agent that actually communicated must not 503 on its FKs.

    ``sessions.agent_id`` and ``message_deliveries.recipient_agent_id`` are
    NOT-NULL FKs to agents; the delete cascades its own dependent rows in one
    transaction. Messages it SENT are preserved (not an FK; peers' inboxes
    still reference them).
    """
    deps, client, operator_key = serve_env
    repos = deps.repos
    ws = "z" * 64
    with deps.connection_factory.unit_of_work() as uow:
        repos.workspaces.upsert(uow, workspace_id=ws)
        for agent_id in ("victim", "peer"):
            repos.agents.upsert(uow, agent_id=agent_id)
        repos.sessions.create(
            uow,
            session_id="s-victim",
            agent_id="victim",
            workspace_id=ws,
            status="active",
        )
        # A message the victim received (delivery as recipient) ...
        repos.messages.create(
            uow,
            message_id="m-in",
            workspace_id=ws,
            from_agent_id="peer",
            target='{"strategy":"direct","agent_id":"victim"}',
            subject="hi",
            body="b",
        )
        repos.deliveries.create(
            uow,
            delivery_id="d-in",
            message_id="m-in",
            recipient_agent_id="victim",
            status="read",
        )
        # ... and one it SENT to a peer (must survive the delete).
        repos.messages.create(
            uow,
            message_id="m-out",
            workspace_id=ws,
            from_agent_id="victim",
            target='{"strategy":"direct","agent_id":"peer"}',
            subject="bye",
            body="b",
        )
        repos.deliveries.create(
            uow,
            delivery_id="d-out",
            message_id="m-out",
            recipient_agent_id="peer",
            status="unread",
        )

    assert (
        client.delete("/api/v1/agents/victim", headers=_h(operator_key)).status_code
        == 200
    )
    assert (
        client.get("/api/v1/agents/victim", headers=_h(operator_key)).status_code == 404
    )
    # The peer and the message the victim sent survive; the peer can still
    # pull it from its inbox.
    with deps.connection_factory.unit_of_work() as uow:
        assert repos.agents.get(uow, "peer") is not None
        assert repos.messages.get(uow, workspace_id=ws, message_id="m-out") is not None


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
            uow,
            session_id="s-alpha",
            agent_id="alpha",
            workspace_id=ws,
            status="active",
        )
        repos.sessions.create(
            uow,
            session_id="s-bravo",
            agent_id="bravo",
            workspace_id=ws,
            status="active",
        )
        import datetime

        old = (
            (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(seconds=300)
            )
            .isoformat()
            .replace("+00:00", "Z")
        )
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
def _seed_full_store(deps) -> None:
    """Populate EVERY operational table - including ``artifacts``, the table
    the original hardcoded wipe list missed (its workspace FK broke the
    reset at commit time on real stores)."""
    ws = "r" * 64
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=ws)
        deps.repos.agents.upsert(uow, agent_id="survivor")
        deps.repos.sessions.create(
            uow,
            session_id="s-reset",
            agent_id="survivor",
            workspace_id=ws,
            status="active",
        )
        deps.repos.messages.create(
            uow,
            message_id="m-reset",
            workspace_id=ws,
            from_agent_id="survivor",
            body="to be wiped",
        )
        deps.repos.deliveries.create(
            uow,
            delivery_id="d-reset",
            message_id="m-reset",
            recipient_agent_id="survivor",
            status="unread",
        )
        uow.connection.execute(
            "INSERT INTO artifacts (artifact_id, workspace_id, artifact_type, "
            "content, created_at) VALUES ('a-reset', ?, 'inline', 'x', "
            "'2026-01-01T00:00:00Z')",
            (ws,),
        )


def _operational_tables(deps) -> list[str]:
    with deps.connection_factory.unit_of_work() as uow:
        rows = uow.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return [
        r["name"]
        for r in rows
        if r["name"] not in ("schema_migrations", "settings", "agents")
    ]


def test_admin_reset_wipes_every_table_but_keeps_agents(serve_env):
    deps, client, operator_key = serve_env
    _seed_full_store(deps)

    response = client.post("/api/v1/admin/reset", headers=_h(operator_key))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["kept_agents"] is True
    assert data["deleted"]["messages"] >= 1
    assert data["deleted"]["artifacts"] >= 1  # the regression table

    tables = _operational_tables(deps)  # own UoW; never nest two write txns
    with deps.connection_factory.unit_of_work() as uow:
        for table in tables:
            count = uow.connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
            assert count == 0, table
        agents = uow.connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        assert agents >= 2  # operator + survivor preserved

    # The operator key still authenticates after the wipe (keys preserved).
    assert client.get("/api/v1/graph", headers=_h(operator_key)).status_code == 200


def test_admin_reset_without_keeping_agents(serve_env):
    deps, client, operator_key = serve_env
    _seed_full_store(deps)

    response = client.post(
        "/api/v1/admin/reset?keep_agents=false", headers=_h(operator_key)
    )
    assert response.status_code == 200
    assert response.json()["data"]["kept_agents"] is False

    with deps.connection_factory.unit_of_work() as uow:
        agents = uow.connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        assert agents == 0
    # Every key died with the agents (cache invalidated synchronously).
    assert client.get("/api/v1/graph", headers=_h(operator_key)).status_code == 401


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

    page = client.get(f"/api/v1/events?after={first}", headers=_h(operator_key)).json()[
        "data"
    ]
    ids = [item["event_id"] for item in page["items"]]
    assert ids == [second]
    assert page["next_cursor"] == second


def _seed_events_ws(deps, ws: str):
    """Upsert the workspace and return an emit(type_, actor) helper."""
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=ws)

    def emit(type_: str, actor: str) -> int:
        with deps.connection_factory.unit_of_work() as uow:
            return deps.event_emitter.emit(
                uow,
                workspace_id=ws,
                stream="workspace",
                type=type_,
                actor_agent_id=actor,
                payload={"t": type_},
            )

    return emit


def test_events_filter_by_type_agent_and_types_endpoint(serve_env):
    """FR1/FR2 (AC1/AC2/AC3): type & agent equality filters (AND-combinable)
    and the distinct-types endpoint; visibility/target travel with each row."""
    deps, client, key = serve_env
    ws = "e" * 64
    emit = _seed_events_ws(deps, ws)
    emit("ev.alpha", "alice")
    emit("ev.alpha", "bob")
    emit("ev.beta", "alice")
    emit("ev.beta", "bob")
    base = {"workspace": ws}

    # AC1: filter by type returns only that type.
    data = client.get(
        "/api/v1/events", params={**base, "type": "ev.alpha"}, headers=_h(key)
    ).json()["data"]
    assert len(data["items"]) == 2
    assert {e["type"] for e in data["items"]} == {"ev.alpha"}

    # AC2: filter by actor agent.
    data = client.get(
        "/api/v1/events", params={**base, "agent": "alice"}, headers=_h(key)
    ).json()["data"]
    assert len(data["items"]) == 2
    assert {e["actor_agent_id"] for e in data["items"]} == {"alice"}

    # AC2: type + agent applies AND.
    data = client.get(
        "/api/v1/events",
        params={**base, "type": "ev.alpha", "agent": "alice"},
        headers=_h(key),
    ).json()["data"]
    assert len(data["items"]) == 1
    assert data["items"][0]["type"] == "ev.alpha"
    assert data["items"][0]["actor_agent_id"] == "alice"
    # visibility/target ship with the row (for the detail modal).
    assert "visibility" in data["items"][0] and "target" in data["items"][0]

    # AC3: distinct types, sorted, no duplicates, scoped by workspace.
    data = client.get(
        "/api/v1/events/types", params={"workspace": ws}, headers=_h(key)
    ).json()["data"]
    assert data["items"] == ["ev.alpha", "ev.beta"]


def test_events_timeline_and_recipient_filter(serve_env):
    deps, client, key = serve_env
    ws = "r" * 64
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=ws)
        deps.event_emitter.emit(
            uow,
            workspace_id=ws,
            stream="workspace",
            type="ev.alpha",
            actor_agent_id="alice",
            target=json.dumps({"strategy": "direct", "agent_id": "bob"}),
        )
        deps.event_emitter.emit(
            uow,
            workspace_id=ws,
            stream="workspace",
            type="ev.alpha",
            actor_agent_id="bob",
            target=json.dumps({"strategy": "direct", "agent_id": "carol"}),
        )
        deps.event_emitter.emit(
            uow,
            workspace_id=ws,
            stream="workspace",
            type="ev.beta",
            actor_agent_id="alice",
            payload={"recipient_agent_id": "bob"},
        )

    now = datetime.now(timezone.utc)
    params = {
        "workspace": ws,
        "recipient": "bob",
        "since": (now - timedelta(days=1)).isoformat(),
        "until": (now + timedelta(days=1)).isoformat(),
    }
    page = client.get("/api/v1/events", params=params, headers=_h(key)).json()["data"]
    assert len(page["items"]) == 2
    assert {event["type"] for event in page["items"]} == {"ev.alpha", "ev.beta"}

    timeline = client.get(
        "/api/v1/events/timeline",
        params={**params, "bucket_seconds": 3600},
        headers=_h(key),
    )
    assert timeline.status_code == 200
    data = timeline.json()["data"]
    assert data["total"] == 2
    assert data["types"] == ["ev.alpha", "ev.beta"]
    assert sum(bucket["total"] for bucket in data["buckets"]) == 2

    too_granular = client.get(
        "/api/v1/events/timeline",
        params={**params, "bucket_seconds": 60},
        headers=_h(key),
    )
    assert too_granular.status_code == 422
    assert "increase the interval" in too_granular.json()["error"]["message"]


def test_handoffs_filter_by_range_and_agents(serve_env):
    deps, client, key = serve_env
    ws = "h" * 64
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=ws)
        uow.connection.executemany(
            """
            INSERT INTO handoffs(
                handoff_id, workspace_id, from_agent_id, target, visibility,
                status, created_at
            ) VALUES (?, ?, ?, ?, 'private', 'OPEN', ?)
            """,
            [
                (
                    "hof_old",
                    ws,
                    "alice",
                    json.dumps({"strategy": "direct", "agent_id": "bob"}),
                    "2026-07-01T10:00:00Z",
                ),
                (
                    "hof_match",
                    ws,
                    "carol",
                    json.dumps({"strategy": "direct", "agent_id": "alice"}),
                    "2026-08-10T10:00:00Z",
                ),
            ],
        )

    response = client.get(
        "/api/v1/handoffs",
        params={
            "workspace": ws,
            "since": "2026-08-01T00:00:00Z",
            "until": "2026-08-31T23:59:59Z",
            "from_agent": "carol",
            "to_agent": "alice",
        },
        headers=_h(key),
    )
    assert response.status_code == 200
    assert [item["handoff_id"] for item in response.json()["data"]["items"]] == [
        "hof_match"
    ]


def test_handoffs_include_terminal_agent_outcomes(serve_env):
    deps, client, key = serve_env
    ws = "o" * 64
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=ws)
        uow.connection.executemany(
            """
            INSERT INTO handoffs(
                handoff_id, workspace_id, from_agent_id, target, visibility,
                status, created_at, claimed_by, result, rejected_reason
            ) VALUES (?, ?, 'creator', ?, 'public', ?, ?, 'worker', ?, ?)
            """,
            [
                (
                    "hof_completed_with_result",
                    ws,
                    json.dumps({"strategy": "broadcast"}),
                    "COMPLETED",
                    "2026-08-10T10:00:00Z",
                    '{"summary":"delivered"}',
                    None,
                ),
                (
                    "hof_rejected_with_reason",
                    ws,
                    json.dumps({"strategy": "broadcast"}),
                    "REJECTED",
                    "2026-08-10T11:00:00Z",
                    None,
                    "Missing required evidence",
                ),
            ],
        )

    response = client.get(
        "/api/v1/handoffs",
        params={"workspace": ws},
        headers=_h(key),
    )
    assert response.status_code == 200
    by_id = {
        item["handoff_id"]: item for item in response.json()["data"]["items"]
    }
    assert by_id["hof_completed_with_result"]["result"] == (
        '{"summary":"delivered"}'
    )
    assert "rejected_reason" not in by_id["hof_completed_with_result"]
    assert by_id["hof_rejected_with_reason"]["rejected_reason"] == (
        "Missing required evidence"
    )
    assert "result" not in by_id["hof_rejected_with_reason"]


def test_meta_harness_sends_messages_and_handoffs_by_audience(
    serve_env, tmp_path
):
    deps, client, key = serve_env
    root = tmp_path / "meta-harness-project"
    root.mkdir()
    root_path = str(root)
    ws = resolve_workspace_id(root_path)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(
            uow,
            workspace_id=ws,
            display_name="Meta-harness test",
            root_realpath=resolve_realpath(root_path),
        )

    for agent_id in ("alpha", "beta"):
        created = client.post(
            "/api/v1/agents",
            json={"agent_id": agent_id},
            headers=_h(key),
        )
        assert created.status_code == 200, created.text

    private_message = client.post(
        "/api/v1/meta-harness/send",
        json={
            "workspace": ws,
            "kind": "message",
            "audience": "private",
            "to_agent_id": "alpha",
            "subject": "Review",
            "body": "Review the policy.",
        },
        headers=_h(key),
    )
    assert private_message.status_code == 200, private_message.text
    private_data = private_message.json()["data"]
    assert private_data["kind"] == "message"
    assert private_data["audience"] == "private"
    assert private_data["recipients"] == ["alpha"]

    broadcast_message = client.post(
        "/api/v1/meta-harness/send",
        json={
            "workspace": ws,
            "kind": "message",
            "audience": "broadcast",
            "body": "Share current status.",
        },
        headers=_h(key),
    )
    assert broadcast_message.status_code == 200, broadcast_message.text
    assert broadcast_message.json()["data"]["audience"] == "broadcast"

    private_handoff = client.post(
        "/api/v1/meta-harness/send",
        json={
            "workspace": ws,
            "kind": "handoff",
            "audience": "private",
            "to_agent_id": "beta",
            "subject": "Implement",
            "body": "Implement the approved change.",
        },
        headers=_h(key),
    )
    assert private_handoff.status_code == 200, private_handoff.text
    assert private_handoff.json()["data"]["notified"] == ["beta"]

    broadcast_handoff = client.post(
        "/api/v1/meta-harness/send",
        json={
            "workspace": ws,
            "kind": "handoff",
            "audience": "broadcast",
            "body": "First available agent: investigate the incident.",
        },
        headers=_h(key),
    )
    assert broadcast_handoff.status_code == 200, broadcast_handoff.text
    assert broadcast_handoff.json()["data"]["audience"] == "broadcast"

    messages = client.get(
        "/api/v1/messages",
        params={"workspace": ws, "agent": "operator", "include_body": "true"},
        headers=_h(key),
    ).json()["data"]["items"]
    private_row = next(row for row in messages if row["subject"] == "Review")
    assert private_row["body"] == "Review the policy."
    assert private_row["target"] == {
        "strategy": "direct",
        "agent_id": "alpha",
    }
    assert [d["recipient_agent_id"] for d in private_row["deliveries"]] == [
        "alpha"
    ]

    handoffs = client.get(
        "/api/v1/handoffs",
        params={"workspace": ws, "from_agent": "operator"},
        headers=_h(key),
    ).json()["data"]["items"]
    by_id = {row["handoff_id"]: row for row in handoffs}
    assert by_id[private_handoff.json()["data"]["handoff_id"]]["target"] == {
        "strategy": "direct",
        "agent_id": "beta",
    }
    assert by_id[broadcast_handoff.json()["data"]["handoff_id"]]["target"] == {
        "strategy": "broadcast"
    }

    missing_agent = client.post(
        "/api/v1/meta-harness/send",
        json={
            "workspace": ws,
            "kind": "message",
            "audience": "private",
            "body": "No target",
        },
        headers=_h(key),
    )
    assert missing_agent.status_code == 422
    assert missing_agent.json()["error"]["code"] == "VALIDATION_ERROR"


def test_events_no_filters_is_backward_compatible(serve_env):
    """AC7: omitting type/agent keeps the exact prior shape (items+next_cursor)."""
    deps, client, key = serve_env
    ws = "f" * 64
    emit = _seed_events_ws(deps, ws)
    emit("ev.solo", "alice")

    data = client.get(
        "/api/v1/events", params={"workspace": ws}, headers=_h(key)
    ).json()["data"]
    assert set(data.keys()) == {"items", "next_cursor"}
    assert len(data["items"]) == 1
    assert data["items"][0]["type"] == "ev.solo"
    assert data["next_cursor"] == data["items"][0]["event_id"]


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
            lambda: (
                _emit_event(deps, ws, "sse.second"),
                _emit_event(deps, ws, "sse.third"),
            ),
        )
        with httpx.Client(timeout=10.0) as client:
            with client.stream(
                "GET",
                f"{base}/api/v1/stream",
                headers={**_h(operator_key), "last-event-id": str(e1)},
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
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


def test_sse_open_stream_does_not_wedge_server_shutdown(tmp_path):
    """Regression: an open SSE feed must not block graceful shutdown.

    The feed's generator is an infinite poll loop, so with a client still
    subscribed nothing cancels it. Flipping ``should_exit`` (exactly what
    CTRL+C does) must let the generator notice and end on its own so the
    server thread drains promptly - instead of hanging on "finalizing" until
    the operator force-kills the terminal. The server here runs WITHOUT a
    graceful-shutdown timeout on purpose: if the generator stops breaking on
    shutdown, this test HANGS (join times out) rather than passing on the
    timeout backstop.
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
    # serve.py wires this so the SSE generator can see shutdown; mirror it.
    app.state.server = server
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
        _emit_event(deps, ws, "sse.before_shutdown")

        base = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=10.0) as client:
            with client.stream(
                "GET", f"{base}/api/v1/stream", headers=_h(operator_key)
            ) as response:
                assert response.status_code == 200
                # Pull the first event so the generator is actively mid-stream.
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        break
                # Client is STILL subscribed. Trigger shutdown like CTRL+C and
                # require the server thread to drain quickly.
                shutdown_at = time.monotonic()
                server.should_exit = True
                thread.join(timeout=10)
                elapsed = time.monotonic() - shutdown_at
        assert not thread.is_alive(), "server hung on the open SSE stream"
        assert elapsed < 8, f"shutdown was not prompt ({elapsed:.1f}s)"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
