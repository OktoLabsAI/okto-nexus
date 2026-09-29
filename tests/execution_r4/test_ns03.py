"""Agent-centric R4 authentication contract and revision tests."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.http import connections_v1
from okto_nexus.bootstrap.dependencies import bootstrap


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
