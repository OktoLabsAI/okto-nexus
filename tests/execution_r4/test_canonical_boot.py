"""Approved canonical boot through the serve lifecycle and durable effect fence."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.adapters.inbound.mcp.tools import harness
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap.embedded_dispatch import EmbeddedDispatchOwner
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, connect_local, wait_receipt, admit


def configure(setup, binding, enabled=True):
    deps, _, client, headers, *_ = setup
    with deps.connection_factory.unit_of_work(write=False) as uow:
        revision = uow.connection.execute("SELECT revision FROM agent_endpoints WHERE endpoint_id=?",
                                          (binding["endpoint_id"],)).fetchone()[0]
    response = client.put(f"/api/v1/harness/endpoints/{binding['endpoint_id']}/boot",
        headers=headers["operator"], json=dict(enabled=enabled, expected_revision=revision))
    assert response.status_code == 200, response.text


def test_serve_boot_uses_core_after_inventory_start_and_replays_once(tmp_path, monkeypatch, request):
    generator = local_setup.__wrapped__(tmp_path, monkeypatch, request)
    setup = next(generator)
    try:
        setup, binding, native = connect_local(setup)
        configure(setup, binding)
        home = setup[0].config.home_dir
        headers, body, candidate, root = setup[3:]
        assert native.opens == 0
    finally:
        generator.close()
    original_init = EmbeddedDispatchOwner.__init__
    def initialize(owner, *args, **kwargs):
        original_init(owner, *args, **kwargs)
        owner.native_factory = native
    monkeypatch.setattr(EmbeddedDispatchOwner, "__init__", initialize)
    def forbidden(*args, **kwargs):
        raise AssertionError("Canonical boot reached the legacy connector")
    monkeypatch.setattr(harness, "construct_profile_connector", forbidden)
    deps = bootstrap({}, ["--home", str(home), "--feature-harness-integrations", "true"])
    app = build_app(deps)
    with TestClient(app) as client:
        current = deps, app, client, headers, body, candidate, root
        first = deps.runtime_boot_status[0]
        assert first["state"] == "ACCEPTED", first
        wait_receipt(current, first)
        replay = harness.run_runtime_boot(deps)[0]
        assert replay["reused"] and replay["operation_id"] == first["operation_id"], replay
        assert native.opens == 1
        with deps.connection_factory.unit_of_work(write=False) as uow:
            proof = json.loads(uow.connection.execute("SELECT boot_authority_json FROM execution_operations").fetchone()[0])
            assert proof["owner_id"] == deps.runtime_dispatcher.owner_id
            assert proof["owner_epoch"] == deps.runtime_dispatcher.epoch
            assert uow.connection.execute("SELECT COUNT(*) FROM harness_sessions").fetchone()[0] == 0
        closed = admit(current, binding, "boot-close", "runtime.close", session_id=first["session_id"])
        wait_receipt(current, closed, stages=("SUCCEEDED",))
        assert native.native.stopped


@pytest.mark.parametrize("change", ["disable", "revision", "issuer"])
def test_boot_approval_is_revalidated_after_admission(connected_local, change):
    setup, binding, native = connected_local
    deps, app, client, _, *_ = setup
    configure(setup, binding)
    lock = app.state.embedded_dispatch_owner.pump.send_lock
    client.portal.call(lock.acquire)
    try:
        boot = harness.run_runtime_boot(deps)[0]
        assert boot["state"] == "ACCEPTED", boot
        if change == "disable":
            configure(setup, binding, False)
        else:
            with deps.connection_factory.unit_of_work() as uow:
                if change == "revision":
                    uow.connection.execute("UPDATE runtime_boot_bindings SET revision=revision+1")
                else:
                    uow.connection.execute("UPDATE agents SET api_key_hash='revoked-operator-key' WHERE agent_id='operator'")
    finally:
        client.portal.call(lock.release)
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT dispatch_state,last_error FROM execution_dispatch_outbox WHERE operation_id=?",
                                         (boot["operation_id"],)).fetchone()
        if row[0] == "RESOLVED_TERMINAL":
            assert "PERMISSION_DENIED" in row[1], row[1]
            break
        assert time.monotonic() < deadline, tuple(row)
        time.sleep(.02)
    assert native.opens == 0


def test_boot_does_not_duplicate_an_existing_canonical_session(connected_local):
    setup, binding, native = connected_local
    opened = admit(setup, binding, "manual-before-boot", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    configure(setup, binding)
    boot = harness.run_runtime_boot(setup[0])[0]
    assert boot["state"] == "blocked" and boot["reason"] == "CONFLICT", boot
    assert native.opens == 1
    closed = admit(setup, binding, "manual-close", "runtime.close", session_id=opened["scope"]["session_id"])
    wait_receipt(setup, closed, stages=("SUCCEEDED",))


def test_boot_rejects_wrong_owner_before_admission(connected_local):
    from okto_nexus.bootstrap.execution_compat import boot_endpoint
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    from okto_nexus.errors import OktoNexusError
    setup, binding, native = connected_local
    deps = setup[0]
    configure(setup, binding)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute("SELECT workspace_id FROM agent_endpoints WHERE endpoint_id=?",
                                           (binding["endpoint_id"],)).fetchone()[0]
    context = RuntimeRequestContext(None, "runtime_boot", represented_agent_id="subject",
        workspace_id=workspace, endpoint_id=binding["endpoint_id"],
        runtime_owner_id=deps.runtime_dispatcher.owner_id, runtime_owner_epoch=deps.runtime_dispatcher.epoch + 1)
    with pytest.raises(OktoNexusError, match="PERMISSION_DENIED"):
        boot_endpoint(deps, context, binding["endpoint_id"], "wrong-owner-boot")
    assert native.opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0
