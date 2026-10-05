"""Core-owned catalog, local candidate and inventory publication checks."""

from dataclasses import replace
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from nexus_connector_core import InstallationCandidate, get_executor_inventory_schema

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.outbound.execution.core_inventory import (
    discover_local_candidates, local_catalog, local_inventory_snapshot,
    resolve_local_installation_selection,
)
from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from okto_nexus.application.executor_inventory import publish_executor_inventory
from okto_nexus.application.executor_inventory_views import read_executor_inventory
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


def test_ns04_05_local_selection_uses_exact_revision_and_installation(tmp_path):
    import nexus_connector_core as core

    candidates = [
        InstallationCandidate(
            adapter_id="codex_app_server", executable=str(tmp_path / name),
            fingerprint="sha256:" + "a" * 64, source="path", trust="selected",
            version="0.157.0", architecture="x86_64",
            build_identity="sha256:" + "b" * 64,
        )
        for name in ("copy-a", "copy-b")
    ]
    revision = core.calculate_inventory_revision(candidates)
    ref_b = core.installation_ref("codex_app_server", candidates[1].executable)
    chosen = resolve_local_installation_selection(
        list(reversed(candidates)), adapter_id="codex_app_server",
        candidate_ref=ref_b, expected_inventory_revision=revision,
    )
    assert chosen.executable == candidates[1].executable
    with pytest.raises(core.CoreError):
        resolve_local_installation_selection(
            candidates, adapter_id="codex_app_server",
            candidate_ref=candidates[0].fingerprint,
            expected_inventory_revision=revision,
        )
    with pytest.raises(core.CoreError):
        resolve_local_installation_selection(
            [replace(candidates[0], fingerprint="sha256:" + "c" * 64),
             candidates[1]], adapter_id="codex_app_server",
            candidate_ref=ref_b, expected_inventory_revision=revision,
        )


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
        # Inventory v2 is generated and versioned by the installed Core.
        # The original HTTP plan remains the source for application envelopes.
        contract["$defs"].update(get_executor_inventory_schema()["$defs"])
        Draft202012Validator(contract["$defs"]["InventoryAccepted"]).validate(
            sent.json())
        assert sent.json()["inventory_revision"] == snapshot["inventory_revision"]
        assert 119_900 <= sent.json()["fresh_for_ms"] <= 120_000
        viewed = client.get(path, headers={
            "Authorization": f"Bearer {key}"})
        assert viewed.status_code == 200
        Draft202012Validator({"$defs": contract["$defs"],
                              **contract["$defs"]["InventoryView"]}).validate(
                                  viewed.json())
        assert viewed.json()["freshness"] == "OFFLINE"
        assert viewed.json()["eligible_for_new_start"] is False
        options = client.get(
            "/v1/agents/agent-a/runtime-options",
            params={"executor_id": info["executor_id"]},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert options.status_code == 200, options.text
        Draft202012Validator({"$defs": contract["$defs"],
                              **contract["$defs"]["RuntimeOptions"]}).validate(
                                  options.json())
        assert all(not row["can_start"] and not row["can_bind"]
                   for row in options.json()["options"])
        assert all(row["technical_state"] == "NOT_INSTALLED"
                   for row in options.json()["options"])
        assert client.get(
            "/v1/agents/another/runtime-options",
            params={"executor_id": info["executor_id"]},
            headers={"Authorization": f"Bearer {key}"},
        ).status_code == 403
        app.state.inventory_fresh_publications[
            (info["server_id"], info["executor_id"])
        ] = (1, time.monotonic() - 121, 0)
        replay = client.put(path, json=snapshot, headers={
            "Authorization": f"Bearer {ticket}"})
        assert replay.status_code == 200
        assert replay.json()["fresh_for_ms"] == 0
        assert client.put(path.replace(info["executor_id"], "other"),
                          json=snapshot, headers={
                              "Authorization": f"Bearer {ticket}"}).status_code == 403
        ambiguous = json.dumps(snapshot)[:-1] + ',"producer_instance_id":"other"}'
        malformed = client.put(path, content=ambiguous,
                               headers={"Authorization": f"Bearer {ticket}"})
        assert malformed.status_code == 400
        assert malformed.json()["error"]["code"] == "VALIDATION_ERROR"
        populated = local_inventory_snapshot([
            InstallationCandidate("codex_app_server", str(tmp_path / "codex"),
                                  "sha256:" + "a" * 64, "explicit", "selected")],
            server_id=info["server_id"], executor_id=info["executor_id"],
            producer_instance_id="producer-a", publication_sequence=2)
        accepted = client.put(path, json=populated, headers={
            "Authorization": f"Bearer {ticket}"})
        assert accepted.status_code == 200, accepted.text
        populated_view = client.get(path, headers={
            "Authorization": f"Bearer {key}"}).json()
        Draft202012Validator({"$defs": contract["$defs"],
                              **contract["$defs"]["InventoryView"]}).validate(populated_view)
        assert populated_view["snapshot"] == populated
        assert populated["evidence"][0]["capability_report"] is None
        assert populated["evidence"][0]["qualified_control_actions"] == []
        assert str(tmp_path) not in json.dumps(populated_view)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "UPDATE execution_executors SET control_state='CONTROL_READY' "
            "WHERE server_id=? AND executor_id=?",
            (info["server_id"], info["executor_id"]),
        )
    assert read_executor_inventory(
        deps.connection_factory, server_id=info["server_id"],
        executor_id=info["executor_id"], agent_id="agent-a",
        fresh_publications={},
    )["freshness"] == "STALE"
