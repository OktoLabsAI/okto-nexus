"""Nexus consumes Core inventory without a Connector or provider binary."""

from __future__ import annotations

from fastapi.testclient import TestClient
from nexus_connector_core import InstallationCandidate

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.outbound.execution.core_inventory import (
    MANAGEMENT_REVISION, local_catalog, local_inventory_snapshot,
)


def test_local_catalog_and_empty_inventory_need_no_runtime():
    catalog = local_catalog()
    assert catalog["format_version"] == 1
    assert any(row["adapter_id"] == "codex_app_server"
               for row in catalog["runtimes"])
    snapshot = local_inventory_snapshot(
        (), server_id="server-a", executor_id="embedded-a",
        producer_instance_id="serve-a", publication_sequence=1,
    )
    assert snapshot["evidence"] == []
    assert all(row["state"] != "READY_FOR_RUNTIME"
               for row in snapshot["availability"]["availability"])


def test_two_copies_keep_distinct_installation_refs(tmp_path):
    candidates = [
        InstallationCandidate(
            adapter_id="codex_app_server", executable=str(tmp_path / name),
            fingerprint="sha256:same-content", source="path", trust="selected",
            version="0.157.0", architecture="x86_64",
            build_identity="sha256:same-build",
        )
        for name in ("first", "second")
    ]
    snapshot = local_inventory_snapshot(
        candidates, server_id="server-a", executor_id="embedded-a",
        producer_instance_id="serve-a", publication_sequence=1,
    )
    refs = {row["candidate_ref"] for row in snapshot["evidence"]}
    assert len(refs) == 2
    assert str(tmp_path) not in str(snapshot)


def test_protocol_is_direct_object_and_does_not_claim_remote_ready(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with TestClient(app) as client:
        response = client.get("/v1/connections/protocol")
    assert response.status_code == 200
    assert response.headers["X-Nexus-Connections-Revision"] == MANAGEMENT_REVISION
    body = response.json()
    assert "ok" not in body and "data" not in body
    assert body["nxl_accepted"] == []
    assert body["remote_execution_ready"] is False
