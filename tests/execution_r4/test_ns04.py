"""Core-owned catalog, local candidate and inventory publication checks."""

from dataclasses import replace
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from nexus_connector_core import InstallationCandidate

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.execution.core_inventory import (
    discover_local_candidates, local_catalog, local_inventory_snapshot,
)
from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from okto_nexus.application.executor_inventory import publish_executor_inventory
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.execution.keys import ExecutorKey
from okto_nexus.errors import OktoNexusError


def test_ns04_01(monkeypatch, tmp_path):
    import nexus_connector_core as core

    monkeypatch.setattr(core, "create_runtime", lambda **_: (_ for _ in ()).throw(
        AssertionError("runtime composed for catalog")))
    catalog = local_catalog()
    assert any(row["adapter_id"] == "codex_app_server" for row in catalog["runtimes"])
    attach = next(row for row in catalog["runtimes"]
                  if row["adapter_id"] == "claude_attach")
    assert attach["support_status"] == "registered_unqualified"
    assert discover_local_candidates(path_env=str(tmp_path)).candidates == ()


def test_ns04_03(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    identity = ensure_execution_installation(deps.connection_factory)
    principal = ExecutorKey(identity.server_id, identity.embedded_executor_id)
    candidates = [
        InstallationCandidate(
            adapter_id="codex_app_server", executable=str(tmp_path / name),
            fingerprint="sha256:" + "a" * 64, source="path", trust="selected",
            version="0.157.0", architecture="x86_64",
            build_identity="sha256:" + "b" * 64,
        )
        for name in ("copy-a", "copy-b")
    ]

    def snapshot(items, seq):
        return local_inventory_snapshot(
            items, server_id=identity.server_id,
            executor_id=identity.embedded_executor_id,
            producer_instance_id="process-one", publication_sequence=seq,
        )

    first = snapshot(candidates, 1)
    published = publish_executor_inventory(
        deps.connection_factory, principal=principal,
        producer_instance_id="process-one", snapshot=first,
    )
    assert published.reused is False
    assert publish_executor_inventory(
        deps.connection_factory, principal=principal,
        producer_instance_id="process-one", snapshot=first,
    ).reused is True
    reordered = snapshot(list(reversed(candidates)), 2)
    assert reordered["inventory_revision"] == first["inventory_revision"]
    publish_executor_inventory(deps.connection_factory, principal=principal,
                               producer_instance_id="process-one", snapshot=reordered)
    changed = snapshot([replace(candidates[0],
                                fingerprint="sha256:" + "c" * 64,
                                build_identity="sha256:" + "d" * 64),
                        candidates[1]], 3)
    assert changed["inventory_revision"] != first["inventory_revision"]
    publish_executor_inventory(deps.connection_factory, principal=principal,
                               producer_instance_id="process-one", snapshot=changed)
    with pytest.raises(OktoNexusError):
        publish_executor_inventory(deps.connection_factory, principal=principal,
                                   producer_instance_id="process-one", snapshot=first)
    tampered = dict(changed)
    tampered["inventory_revision"] = first["inventory_revision"]
    with pytest.raises(OktoNexusError):
        publish_executor_inventory(deps.connection_factory, principal=principal,
                                   producer_instance_id="process-one", snapshot=tampered)
    with pytest.raises(OktoNexusError):
        publish_executor_inventory(deps.connection_factory, principal=principal,
                                   producer_instance_id="other-process", snapshot=changed)
    successor = local_inventory_snapshot(
        candidates, server_id=identity.server_id,
        executor_id=identity.embedded_executor_id,
        producer_instance_id="other-process", publication_sequence=4,
    )
    with pytest.raises(OktoNexusError):
        publish_executor_inventory(deps.connection_factory, principal=principal,
                                   producer_instance_id="other-process",
                                   snapshot=successor)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        current = uow.connection.execute(
            "SELECT publication_sequence,inventory_revision,previous_revision "
            "FROM execution_inventory_current WHERE server_id=? AND executor_id=?",
            (principal.server_id, principal.executor_id),
        ).fetchone()
        count = uow.connection.execute("SELECT COUNT(*) FROM execution_inventory_snapshots "
                                       "WHERE server_id=? AND executor_id=?",
                                       (principal.server_id, principal.executor_id)).fetchone()[0]
        projections = [row[0] for row in uow.connection.execute(
            "SELECT canonical_projection FROM execution_inventory_snapshots")]
    assert tuple(current) == (3, changed["inventory_revision"], first["inventory_revision"])
    assert count == 2
    assert all(str(tmp_path) not in projection for projection in projections)


def test_remote_inventory_http_requires_executor_ticket(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agents(agent_id,created_at) "
                               "VALUES (?,?)",
                               ("agent-a", "2026-09-29T00:00:00Z"))
    with deps.connection_factory.unit_of_work() as uow:
        key = app.state.auth.issue_key(uow, agent_id="agent-a")
    with TestClient(app, raise_server_exceptions=False) as client:
        registered = client.post(
            "/v1/connections/executors:register",
            json={"client_intent_id": "register-a", "connector_id": "connector-a",
                  "label": "Remote host", "control_capabilities": []},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert registered.status_code == 201, registered.text
        info = registered.json()
        path = f"/v1/runtime/executors/{info['executor_id']}/inventory"
        snapshot = local_inventory_snapshot(
            [], server_id=info["server_id"], executor_id=info["executor_id"],
            producer_instance_id="producer-a", publication_sequence=1,
        )
        assert client.put(path, json=snapshot).status_code == 401
        assert client.put(path, json=snapshot, headers={
            "Authorization": f"Bearer {key}"}).status_code == 403
        ticket = info["bootstrap_ticket"]["ticket"]
        sent = client.put(path, json=snapshot, headers={
            "Authorization": f"Bearer {ticket}"})
        assert sent.status_code == 200, sent.text
        contract = json.loads((Path(__file__).resolve().parents[2] /
                               "plans/contratos/http-target.schema.json").read_text(
                                   encoding="utf-8"))
        Draft202012Validator(contract["$defs"]["InventoryAccepted"]).validate(
            sent.json())
        assert sent.json()["inventory_revision"] == snapshot["inventory_revision"]
        assert sent.json()["fresh_for_ms"] == 120_000
        assert client.put(path, json=snapshot, headers={
            "Authorization": f"Bearer {ticket}"}).status_code == 200
        assert client.put(path.replace(info["executor_id"], "other"),
                          json=snapshot, headers={
                              "Authorization": f"Bearer {ticket}"}).status_code == 403
        ambiguous = json.dumps(snapshot)[:-1] + ',"producer_instance_id":"other"}'
        malformed = client.put(path, content=ambiguous,
                               headers={"Authorization": f"Bearer {ticket}"})
        assert malformed.status_code == 400
        assert malformed.json()["error"]["code"] == "VALIDATION_ERROR"
