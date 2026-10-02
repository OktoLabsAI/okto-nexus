"""Nexus consumes Core inventory without a Connector or provider binary."""

from __future__ import annotations

from fastapi.testclient import TestClient
from nexus_connector_core import InstallationCandidate

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.outbound.execution.core_inventory import (
    MANAGEMENT_REVISION, discover_local_candidates, local_catalog,
    local_inventory_snapshot,
)


def test_local_catalog_and_empty_inventory_need_no_runtime():
    catalog = local_catalog()
    assert catalog["format_version"] == 2
    assert any(row["adapter_id"] == "codex_app_server"
               for row in catalog["runtimes"])
    snapshot = local_inventory_snapshot(
        (), server_id="server-a", executor_id="embedded-a",
        producer_instance_id="serve-a", publication_sequence=1,
    )
    assert snapshot["evidence"] == []
    assert snapshot["catalog"] == catalog
    pi = next(row for row in catalog["runtimes"] if row["adapter_id"] == "pi_rpc")
    steer = next(control for control in pi["control_targeting"] if control["action"] == "turn.steer")
    assert steer["native_turn_id"] == "forbidden"
    assert steer["steer_timing"] == "NEXT_TURN_BOUNDARY"
    assert all(row["state"] != "READY_FOR_RUNTIME"
               for row in snapshot["availability"]["availability"])


def test_local_discovery_calls_public_core_facade_without_runtime(tmp_path):
    found = discover_local_candidates(path_env=str(tmp_path))
    assert found.candidates == ()


def test_two_copies_keep_distinct_installation_refs(tmp_path):
    candidates = [
        InstallationCandidate(
            adapter_id="codex_app_server", executable=str(tmp_path / name),
            fingerprint="sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", source="path", trust="selected",
            version="0.157.0", architecture="x86_64",
            build_identity="sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        )
        for name in ("first", "second")
    ]
    snapshot = local_inventory_snapshot(
        candidates, server_id="server-a", executor_id="embedded-a",
        producer_instance_id="serve-a", publication_sequence=1,
    )
    refs = {row["candidate_ref"] for row in snapshot["evidence"]}
    assert len(refs) == 2
    assert all(row["qualified_control_actions"] == [] for row in snapshot["evidence"])
    assert str(tmp_path) not in str(snapshot)


def test_protocol_advertises_executable_r4_and_preserves_historical_r3(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with TestClient(app) as client:
        response = client.get("/v1/connections/protocol")
    assert response.status_code == 200
    assert response.headers["X-Nexus-Connections-Revision"] == MANAGEMENT_REVISION
    body = response.json()
    assert "ok" not in body and "data" not in body
    assert body["nxl_accepted"] == ["nxl-1-agent-centric-http-only-2026-09-29-r4"]
    assert body["remote_execution_ready"] is True
    assert body["nxl_historical_revision"].endswith("-r3")


def test_contract_promotion_does_not_override_host_readiness(monkeypatch):
    from okto_nexus.adapters.outbound.execution import core_inventory
    monkeypatch.setattr(core_inventory, "SERVER_R4_EXECUTION_READY", False)
    info = core_inventory.protocol_info()
    assert info["remote_execution_ready"] is False
    assert info["nxl_accepted"] == []


def test_revision_alias_alone_cannot_enable_unexecutable_bundle(monkeypatch):
    from okto_nexus.adapters.outbound.execution import core_inventory
    import nexus_connector_core as core
    facts = core.verify_r4_bundle()
    monkeypatch.setattr(core, "verify_r4_bundle", lambda: {**facts, "executable": False})
    assert core_inventory.protocol_info()["remote_execution_ready"] is False
