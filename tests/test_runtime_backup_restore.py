"""Exercise the operator's combined offline procedure on production runtime data."""
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.application.runtime_shutdown import shutdown_runtime
from test_pr34_remediation import runtime as runtime_fixture, send_message, open_rest
from test_runtime_artifact_durability import large_output_session
from test_runtime_result_publication import result

runtime = runtime_fixture
spec = importlib.util.spec_from_file_location("offline_runtime_backup",
    Path(__file__).parents[1] / "tools/offline_runtime_backup.py")
procedure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(procedure)


def quiesced_snapshot(runtime, tmp_path):
    deps = runtime[0]
    large_output_session(runtime)
    source = send_message(runtime, body="backup fixture")
    published = result(runtime, source["runtime_operations"][0], "PUBLISHED")
    assert published["output_artifact_id"]
    assert shutdown_runtime(deps.runtime_dispatcher, deps.harness_supervisor)["state"] == "drained"
    snapshot = tmp_path / "snapshot"
    report = procedure.backup(deps.config.home_dir, snapshot, stopped=True)
    return snapshot, report, source, published






def test_backup_refuses_active_owner_and_requires_explicit_quiescence(runtime, tmp_path):
    deps = runtime[0]
    destination = tmp_path / "refused"
    with pytest.raises(ValueError, match="acknowledgement"):
        procedure.backup(deps.config.home_dir, destination)
    with pytest.raises((OSError, ValueError)):
        procedure.backup(deps.config.home_dir, destination, stopped=True)
    assert not destination.exists()






def test_offline_backup_still_refuses_an_unexpired_owner_lease(runtime, tmp_path):
    from okto_nexus.domain.base import iso_plus
    deps = runtime[0]
    assert shutdown_runtime(deps.runtime_dispatcher, deps.harness_supervisor)["state"] == "drained"
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_dispatcher_owner SET lease_expires_at=?",
            (iso_plus(deps.clock.now_iso(), 300),))
    with pytest.raises(ValueError, match="lease is still live"):
        procedure.backup(deps.config.home_dir, tmp_path / "refused", stopped=True)
    assert not (tmp_path / "refused").exists()
