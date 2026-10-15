"""Current harness edits atomically retire old consent without changing identity."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_boot import configure
from test_canonical_grant_regressions import mcp_helpers, open_scoped, invoke_command


def snapshot(setup, binding):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return {name: [dict(r) for r in uow.connection.execute(query, (binding["endpoint_id"],))] for name, query in {
            "endpoint": "SELECT * FROM agent_endpoints WHERE endpoint_id=?",
            "grants": "SELECT * FROM runtime_execution_grants WHERE endpoint_id=?",
            "boot": "SELECT * FROM runtime_boot_bindings WHERE endpoint_id=?",
            "audit": "SELECT * FROM runtime_access_audit WHERE action='config.endpoint.update' AND resource_id=?",
        }.items()}


@pytest.mark.parametrize("setting", ["harness-settings", "tool-permission"])
def test_settings_cas_preserves_other_config_and_invalidates_boot_and_grants(connected_local, setting):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    configure(setup, binding)
    before = snapshot(setup, binding)
    path = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/{setting}"
    value = dict(settings=dict(model="test-model", effort="high")) if setting == "harness-settings" else dict(mode="always_allow")
    body = dict(expected_revision=before["endpoint"][0]["revision"], **value)
    assert client.put(path, headers=headers["subject"], json=body).status_code == 403
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.put(path, headers=headers["operator"], json=body), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    after = snapshot(setup, binding)
    assert after["endpoint"][0]["revision"] == before["endpoint"][0]["revision"] + 1
    old = json.loads(before["endpoint"][0]["public_config"])
    current = json.loads(after["endpoint"][0]["public_config"])
    field = "harness_settings" if setting == "harness-settings" else "nexus_tool_permission"
    assert {k: v for k, v in current.items() if k != field} == {k: v for k, v in old.items() if k != field}
    assert all(g["revoked_at"] for g in after["grants"])
    assert after["boot"][0]["enabled"] == 0
    assert len(after["audit"]) == len(before["audit"]) + 1
    audit = after["audit"][-1]
    assert json.loads(audit["changed_fields"]) == [field]
    assert audit["old_revision"] == before["endpoint"][0]["revision"]
    assert str(setup[-1]) not in str(audit)
    # Returning to the former value is another edit, not restored consent.
    reset = dict(settings={}) if setting == "harness-settings" else dict(mode="ask")
    response = client.put(path, headers=headers["operator"], json=dict(expected_revision=audit["new_revision"], **reset))
    assert response.status_code == 200, response.text
    final = snapshot(setup, binding)
    assert all(g["revoked_at"] for g in final["grants"]) and final["boot"][0]["enabled"] == 0
    assert native.opens == 0


@pytest.mark.parametrize("setting", ["harness-settings", "tool-permission"])
def test_failed_settings_commit_rolls_back_config_grants_boot_and_audit(connected_local, monkeypatch, setting):
    from okto_nexus.adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
    setup, binding, native = connected_local
    _, _, client, headers, *_ = setup
    configure(setup, binding)
    before = snapshot(setup, binding)
    original = SqliteEndpointRepo.audit_configuration
    def cut(self, uow, **kwargs):
        original(self, uow, **kwargs)
        raise OSError("Fixture configuration commit failure")
    monkeypatch.setattr(SqliteEndpointRepo, "audit_configuration", cut)
    value = dict(settings=dict(model="test-model")) if setting == "harness-settings" else dict(mode="always_allow")
    response = client.put(f"/api/v1/harness/endpoints/{binding['endpoint_id']}/{setting}", headers=headers["operator"],
        json=dict(expected_revision=before["endpoint"][0]["revision"], **value))
    assert response.status_code == 500, response.text
    assert snapshot(setup, binding) == before
    assert native.opens == 0


@pytest.mark.parametrize("setting", ["harness-settings", "tool-permission"])
def test_live_session_refuses_launch_changes_and_preserves_authority(connected_local, setting):
    setup, binding, native = connected_local
    _, _, client, headers, *_ = setup
    opened = admit(setup, binding, "live-before-config", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    before = snapshot(setup, binding)
    value = dict(settings=dict(model="test-model")) if setting == "harness-settings" else dict(mode="always_allow")
    response = client.put(f"/api/v1/harness/endpoints/{binding['endpoint_id']}/{setting}", headers=headers["operator"],
        json=dict(expected_revision=before["endpoint"][0]["revision"], **value))
    assert response.status_code == 409, response.text
    assert snapshot(setup, binding) == before
    closed = admit(setup, binding, "close-after-rejected-config", "runtime.close", session_id=opened["scope"]["session_id"])
    wait_receipt(setup, closed, stages=("SUCCEEDED",))
    assert native.native.stopped and native.opens == 1
