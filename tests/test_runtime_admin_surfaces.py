"""Administrative runtime operations use identical authenticated services."""
import json
import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool

runtime = runtime_fixture




def test_admin_profiles_are_redacted_on_both_surfaces(runtime):
    deps, client, root, _, operator, _ = runtime
    # Retained historical records must remain redacted without using removed
    # setup APIs to create a new executable legacy profile.
    with deps.connection_factory.unit_of_work() as uow:
        now = deps.clock.now_iso()
        uow.connection.execute('INSERT INTO runtime_profiles(profile_id,adapter_id,config,secret_refs,created_at,updated_at) VALUES(?,?,?,?,?,?)',
            ('private-profile', 'codex', json.dumps({'env': {'CODEX_HOME': root}}),
             json.dumps({'FIXTURE_KEY': 'env:FIXTURE_SOURCE'}), now, now))
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
    from test_runtime_production_multiplex import retained_profile, retained_endpoint
    retained_profile(runtime)
    retained_endpoint(runtime, "endpoint-pi")
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
