"""Administrative runtime operations use identical authenticated services."""
import json
import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool

runtime = runtime_fixture


def test_mcp_endpoint_administration_matches_rest_and_keeps_cas(runtime):
    _, client, root, _, operator, _ = runtime
    created = tool(client, operator, "harness_list", {"view": "profiles", "maintenance": {
        "action": "create", "profile_id": "admin-profile", "adapter_id": "codex", "enabled": True}})
    assert created["ok"], created
    created = tool(client, operator, "harness_list", {"view": "endpoints", "maintenance": json.dumps({
        "action": "create", "endpoint_id": "admin-endpoint", "agent_id": "worker", "adapter_id": "codex",
        "project_root": root, "profile_id": "admin-profile", "enabled": True})})
    assert created["ok"], created
    mcp = tool(client, operator, "harness_list", {"view": "endpoints"})
    rest = client.get("/api/v1/harness/endpoints", headers={"x-api-key": operator})
    assert mcp["ok"] and mcp["data"] == rest.json()["data"]
    updated = tool(client, operator, "harness_list", {"view": "endpoints", "maintenance": {
        "action": "update", "endpoint_id": "admin-endpoint", "expected_revision": 1, "public_config": {}}})
    assert updated["ok"] and updated["data"]["revision"] == 2, updated
    stale = client.patch("/api/v1/harness/endpoints/admin-endpoint", headers={"x-api-key": operator},
        json={"expected_revision": 1, "public_config": {}})
    assert stale.status_code == 409, stale.text
    boot = tool(client, operator, "harness_list", {"view": "endpoints", "maintenance": {
        "action": "boot", "endpoint_id": "admin-endpoint", "expected_revision": 2, "enabled": False}})
    assert boot["ok"] and boot["data"]["boot_enabled"] is False, boot


def test_admin_profiles_are_redacted_on_both_surfaces(runtime):
    _, client, root, _, operator, _ = runtime
    response = client.post("/api/v1/harness/profiles", headers={"x-api-key": operator}, json={
        "profile_id": "private-profile", "adapter_id": "codex", "config": {"env": {"CODEX_HOME": root}},
        "secret_refs": {"FIXTURE_KEY": "env:FIXTURE_SOURCE"}})
    assert response.status_code == 200, response.text
    mcp = tool(client, operator, "harness_list", {"view": "profiles"})
    rest = client.get("/api/v1/harness/profiles", headers={"x-api-key": operator})
    assert mcp["ok"] and rest.status_code == 200, (mcp, rest.text)
    assert mcp["data"] == rest.json()["data"]
    rendered = json.dumps(mcp["data"])
    assert root not in rendered and "FIXTURE_SOURCE" not in rendered and "FIXTURE_KEY" not in rendered
    assert "private-profile" in rendered


def test_admin_payload_validation_and_authority_are_shared(runtime):
    deps, client, _, peers, operator, caller = runtime
    body = {"profile_id": "bad-profile", "adapter_id": "codex", "enabled": True, "actor_agent_id": "operator"}
    mcp = tool(client, operator, "harness_list", {"view": "profiles", "maintenance": {"action": "create", **body}})
    rest = client.post("/api/v1/harness/profiles", headers={"x-api-key": operator}, json=body)
    assert not mcp["ok"] and mcp["error"]["code"] == "VALIDATION_ERROR", mcp
    assert rest.status_code == 422, rest.text
    denied = tool(client, caller, "harness_list", {"view": "endpoints"})
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    deps.config.feature_harness_integrations = False
    cached = tool(client, operator, "harness_list", {"view": "endpoints"})
    assert not cached["ok"], cached
    assert not peers


@pytest.mark.parametrize("change", [{"enabled": "true"}, {"inherit_ambient": 1},
    {"config": []}, {"profile_id": ""}, {"secret_refs": {"KEY": 12}}])
def test_profile_validation_never_coerces_authority_or_configuration(runtime, change):
    deps, client, _, _, operator, _ = runtime
    body = {"profile_id": "invalid-profile", "adapter_id": "codex", **change}
    rest = client.post("/api/v1/harness/profiles", headers={"x-api-key": operator}, json=body)
    mcp = tool(client, operator, "harness_list", {"view": "profiles", "maintenance": {"action": "create", **body}})
    assert rest.status_code == 422, rest.text
    assert not mcp["ok"] and mcp["error"]["code"] == "VALIDATION_ERROR", mcp
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute("SELECT 1 FROM runtime_profiles WHERE profile_id='invalid-profile'").fetchone()


def test_reconciliation_retry_across_mcp_and_rest_does_not_spawn(runtime):
    deps, client, _, peers, operator, caller = runtime
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET health='quarantined',health_reason='owner_lost' WHERE endpoint_id='endpoint-pi'")
    args = {"action": "reconcile", "endpoint_id": "endpoint-pi", "expected_revision": 1,
        "idempotency_key": "cross-surface-reconcile", "reason": "Reviewed disposable owner"}
    denied = tool(client, operator, "harness_list", {"view": "endpoints", "maintenance": args})
    assert not denied["ok"] and denied["error"]["code"] == "VALIDATION_ERROR", denied
    args["acknowledge_uncertain_effects"] = True
    denied = tool(client, caller, "harness_list", {"view": "endpoints", "maintenance": args})
    assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED", denied
    mcp = tool(client, operator, "harness_list", {"view": "endpoints", "maintenance": args})
    assert mcp["ok"], mcp
    body = {k: v for k, v in args.items() if k not in {"action", "endpoint_id"}}
    rest = client.post("/api/v1/harness/endpoints/endpoint-pi/reconcile", headers={"x-api-key": operator}, json=body)
    assert rest.status_code == 200, rest.text
    assert rest.json()["data"]["replayed"] is True
    assert rest.json()["data"]["reconciliation_id"] == mcp["data"]["reconciliation_id"]
    assert not peers
