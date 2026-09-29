"""Agent-centric R4 authentication contract and revision tests."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.http import connections_v1
from okto_nexus.adapters.outbound.sqlite.execution_identity import (
    ensure_execution_installation, register_remote_executor,
)
from okto_nexus.adapters.outbound.sqlite.execution_tickets import (
    issue_execution_ticket, verify_execution_ticket,
)
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.errors import OktoNexusError


def test_ns03_01(tmp_path):
    """One bearer resolves by the existing key index among 100,000 agents."""
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    factory = deps.connection_factory
    stamp = "2026-09-29T00:00:00Z"
    with factory.unit_of_work() as uow:
        uow.connection.executemany(
            "INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
            ((f"other-{index:06d}", stamp) for index in range(100_000)),
        )
        uow.connection.execute(
            "INSERT INTO agents(agent_id,created_at,metadata) VALUES (?,?,?)",
            ("agent-target", stamp, json.dumps({"display_name": "Target"})),
        )
    app = build_app(deps)
    with factory.unit_of_work() as uow:
        first_key = app.state.auth.issue_key(uow, agent_id="agent-target")
    with factory.unit_of_work(write=False) as uow:
        query = uow.connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM agents WHERE api_key_hash=?",
            ("f" * 64,),
        ).fetchall()
    assert any("idx_agents_api_key_hash" in str(row[3]) for row in query)

    with TestClient(app, raise_server_exceptions=False) as client:
        unauthenticated = client.get("/v1/connections/me")
        assert unauthenticated.status_code == 401
        first = client.get("/v1/connections/me", headers={
            "Authorization": f"Bearer {first_key}",
            "X-Nexus-Agent-Hint": "agent-target",
        })
        assert first.status_code == 200, first.text
        body = first.json()
        contract = json.loads((Path(__file__).resolve().parents[2] /
                               "plans/contratos/http-target.schema.json").read_text(
                                   encoding="utf-8"))
        Draft202012Validator(contract["$defs"]["MeInfo"]).validate(body)
        assert "ok" not in body and "data" not in body
        assert body["agent_id"] == "agent-target"
        assert body["display_name"] == "Target"
        assert body["server_id"].startswith("srv_")
        assert body["revisions"] == {
            "authorization": 1, "configuration": 1, "credential_epoch": 1,
        }
        assert "messages.send_direct" in body["permissions"]
        assert first.headers["X-Nexus-Connections-Revision"].endswith("-r4")

        spoof = client.get("/v1/connections/me", headers={
            "Authorization": f"Bearer {first_key}",
            "X-Nexus-Agent-Hint": "other-000001",
        })
        assert spoof.status_code == 403
        assert spoof.json()["error"]["code"] == "SCOPE_MISMATCH"
        assert "other-000001" not in spoof.text

        with factory.unit_of_work() as uow:
            uow.connection.execute(
                "UPDATE agents SET permissions=? WHERE agent_id='agent-target'",
                (json.dumps({"messages": {"send_direct": False}}),),
            )
        changed = client.get("/v1/connections/me", headers={
            "Authorization": f"Bearer {first_key}"})
        assert changed.status_code == 200
        assert changed.json()["revisions"] == {
            "authorization": 2, "configuration": 1, "credential_epoch": 1,
        }
        assert "messages.send_direct" not in changed.json()["permissions"]

        with factory.unit_of_work() as uow:
            uow.connection.execute(
                "UPDATE agents SET metadata=? WHERE agent_id='agent-target'",
                (json.dumps({"display_name": "Target Updated"}),),
            )
        configured = client.get("/v1/connections/me", headers={
            "Authorization": f"Bearer {first_key}"})
        assert configured.status_code == 200
        assert configured.json()["display_name"] == "Target Updated"
        assert configured.json()["revisions"] == {
            "authorization": 2, "configuration": 2, "credential_epoch": 1,
        }

        with factory.unit_of_work() as uow:
            second_key = app.state.auth.issue_key(uow, agent_id="agent-target")
        assert client.get("/v1/connections/me", headers={
            "Authorization": f"Bearer {first_key}"}).status_code == 401
        rotated = client.get("/v1/connections/me", headers={
            "Authorization": f"Bearer {second_key}"})
        assert rotated.status_code == 200
        assert rotated.json()["revisions"]["credential_epoch"] == 2

        def broken_revisions(*_args, **_kwargs):
            raise RuntimeError("sensitive internal detail")

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(connections_v1, "current_agent_revisions", broken_revisions)
            failed = client.get("/v1/connections/me", headers={
                "Authorization": f"Bearer {second_key}"})
        assert failed.status_code == 500
        assert failed.json()["error"]["code"] == "INTERNAL"
        assert "ok" not in failed.json()
        assert "sensitive internal detail" not in failed.text


def test_ns03_03(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    factory = deps.connection_factory
    server_id = ensure_execution_installation(factory).server_id
    app = build_app(deps)
    with factory.unit_of_work() as uow:
        for agent_id in ("agent-a", "agent-b"):
            uow.connection.execute("INSERT INTO agents(agent_id,created_at) "
                                   "VALUES (?,?)",
                                   (agent_id, "2026-09-29T00:00:00Z"))
    with factory.unit_of_work() as uow:
        app.state.auth.issue_key(uow, agent_id="agent-a")
        app.state.auth.issue_key(uow, agent_id="agent-b")
    executor_a = register_remote_executor(
        factory, actor_agent_id="agent-a", connector_id="connector-a",
        client_intent_id="register-a",
    ).executor_id
    executor_b = register_remote_executor(
        factory, actor_agent_id="agent-b", connector_id="connector-b",
        client_intent_id="register-b",
    ).executor_id
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    issued = issue_execution_ticket(
        factory, server_id=server_id, executor_id=executor_a,
        agent_id="agent-a", now=now, expires_in=60,
    )
    assert issued.audience == "nexus-executor-control"
    assert set(issued.scopes) == {"link:connect", "inventory:publish"}
    assert verify_execution_ticket(
        factory, ticket=issued.ticket, server_id=server_id,
        executor_id=executor_a, scope="inventory:publish", now=now,
    ).agent_id == "agent-a"
    for target, scope, instant in (
        (executor_b, "inventory:publish", now),
        (executor_a, "receipt:publish", now),
        (executor_a, "inventory:publish", now + timedelta(seconds=60)),
    ):
        with pytest.raises(OktoNexusError):
            verify_execution_ticket(
                factory, ticket=issued.ticket, server_id=server_id,
                executor_id=target, scope=scope, now=instant,
            )
    with pytest.raises(OktoNexusError):
        issue_execution_ticket(
            factory, server_id=server_id, executor_id=executor_b,
            agent_id="agent-a", now=now,
        )
    with factory.unit_of_work() as uow:
        app.state.auth.issue_key(uow, agent_id="agent-a")
    with pytest.raises(OktoNexusError):
        verify_execution_ticket(
            factory, ticket=issued.ticket, server_id=server_id,
            executor_id=executor_a, scope="inventory:publish", now=now,
        )
    assert verify_execution_ticket(
        factory, ticket=issue_execution_ticket(
            factory, server_id=server_id, executor_id=executor_b,
            agent_id="agent-b", now=now,
        ).ticket, server_id=server_id, executor_id=executor_b,
        scope="inventory:publish", now=now,
    ).agent_id == "agent-b"
    fresh_a = issue_execution_ticket(
        factory, server_id=server_id, executor_id=executor_a,
        agent_id="agent-a", now=now,
    )
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_executors SET revoked_at=? WHERE server_id=? "
            "AND executor_id=?", (now.isoformat(), server_id, executor_a),
        )
    with pytest.raises(OktoNexusError):
        verify_execution_ticket(
            factory, ticket=fresh_a.ticket, server_id=server_id,
            executor_id=executor_a, scope="inventory:publish", now=now,
        )


def test_binding_ticket_follows_endpoint_agent_not_executor_registrar(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    factory = deps.connection_factory
    server_id = ensure_execution_installation(factory).server_id
    app = build_app(deps)
    stamp = "2026-09-29T00:00:00Z"
    with factory.unit_of_work() as uow:
        for agent_id in ("registrar", "lane-agent"):
            uow.connection.execute(
                "INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
                (agent_id, stamp),
            )
            app.state.auth.issue_key(uow, agent_id=agent_id)
        uow.connection.execute(
            "INSERT INTO workspaces(workspace_id,created_at) VALUES ('ws',?)",
            (stamp,),
        )
        uow.connection.execute(
            "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
            "adapter_id,protocol,enabled,created_at,updated_at) "
            "VALUES ('endpoint','lane-agent','ws','codex','native',0,?,?)",
            (stamp, stamp),
        )
    executor_id = register_remote_executor(
        factory, actor_agent_id="registrar", connector_id="connector",
        client_intent_id="register",
    ).executor_id
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO execution_workspace_bindings(server_id,"
            "workspace_binding_id,executor_id,workspace_id,realization_handle,"
            "revision,status) VALUES (?,?,?,?,?,1,'READY')",
            (server_id, "workspace-binding", executor_id, "ws",
             "root_1234567890123456"),
        )
        uow.connection.execute(
            "INSERT INTO execution_bindings(server_id,binding_id,executor_id,"
            "endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,"
            "realization_ref,realization_revision,binding_revision) "
            "VALUES (?,?,?,?,?,?,?,?,1,1)",
            (server_id, "binding", executor_id, "endpoint",
             "workspace-binding", "candidate", "sha256:" + "a" * 64,
             "realization"),
        )
    issued = issue_execution_ticket(
        factory, server_id=server_id, executor_id=executor_id,
        agent_id="lane-agent", binding_id="binding",
        scopes=frozenset({"receipt:publish"}),
    )
    assert verify_execution_ticket(
        factory, ticket=issued.ticket, server_id=server_id,
        executor_id=executor_id, binding_id="binding",
        scope="receipt:publish",
    ).agent_id == "lane-agent"
    with pytest.raises(OktoNexusError):
        issue_execution_ticket(
            factory, server_id=server_id, executor_id=executor_id,
            agent_id="registrar", binding_id="binding",
            scopes=frozenset({"receipt:publish"}),
        )
    with pytest.raises(OktoNexusError):
        issue_execution_ticket(
            factory, server_id=server_id, executor_id=executor_id,
            agent_id="lane-agent",
        )
    with factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE agent_endpoints SET agent_id='registrar' "
            "WHERE endpoint_id='endpoint'",
        )
    with pytest.raises(OktoNexusError):
        verify_execution_ticket(
            factory, ticket=issued.ticket, server_id=server_id,
            executor_id=executor_id, binding_id="binding",
            scope="receipt:publish",
        )


def test_register_executor_is_scoped_and_returns_only_bootstrap_authority(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    factory = deps.connection_factory
    app = build_app(deps)
    with factory.unit_of_work() as uow:
        for agent_id in ("agent-a", "agent-b"):
            uow.connection.execute("INSERT INTO agents(agent_id,created_at) "
                                   "VALUES (?,?)",
                                   (agent_id, "2026-09-29T00:00:00Z"))
    with factory.unit_of_work() as uow:
        key_a = app.state.auth.issue_key(uow, agent_id="agent-a")
        key_b = app.state.auth.issue_key(uow, agent_id="agent-b")
    body = {"client_intent_id": "register-a", "connector_id": "connector-a",
            "label": "Remote host", "control_capabilities": []}
    path = "/v1/connections/executors:register"
    with TestClient(app, raise_server_exceptions=False) as client:
        first = client.post(path, json=body, headers={
            "Authorization": f"Bearer {key_a}"})
        assert first.status_code == 201, first.text
        contract = json.loads((Path(__file__).resolve().parents[2] /
                               "plans/contratos/http-target.schema.json").read_text(
                                   encoding="utf-8"))
        schema = {"$defs": contract["$defs"],
                  **contract["$defs"]["RegisterExecutorResponse"]}
        Draft202012Validator(schema).validate(first.json())
        assert first.json()["state"] == "AWAITING_INVENTORY"
        assert first.json()["bootstrap_ticket"]["scopes"] == [
            "inventory:publish", "link:connect"]
        assert first.headers["Cache-Control"] == "no-store"
        retry = client.post(path, json=body, headers={
            "Authorization": f"Bearer {key_a}"})
        assert retry.status_code == 200
        assert retry.json()["executor_id"] == first.json()["executor_id"]
        assert retry.json()["bootstrap_ticket"]["ticket"] != (
            first.json()["bootstrap_ticket"]["ticket"])
        with pytest.raises(OktoNexusError):
            verify_execution_ticket(
                factory, ticket=first.json()["bootstrap_ticket"]["ticket"],
                server_id=first.json()["server_id"],
                executor_id=first.json()["executor_id"],
                scope="inventory:publish",
            )
        assert verify_execution_ticket(
            factory, ticket=retry.json()["bootstrap_ticket"]["ticket"],
            server_id=retry.json()["server_id"],
            executor_id=retry.json()["executor_id"],
            scope="inventory:publish",
        ).agent_id == "agent-a"
        changed = client.post(path, json={**body, "label": "Different"},
                              headers={"Authorization": f"Bearer {key_a}"})
        assert changed.status_code == 409
        assert changed.json()["error"]["code"] == "CONFLICT"
        foreign = client.post(path, json={**body, "client_intent_id": "other"},
                              headers={"Authorization": f"Bearer {key_b}"})
        assert foreign.status_code == 409
        invalid = client.post(path, json={**body, "raw_executable": "C:/bin"},
                              headers={"Authorization": f"Bearer {key_a}"})
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "ok" not in invalid.json()
