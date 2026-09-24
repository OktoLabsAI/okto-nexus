"""Declared native requirements restrict execution; they do not grant features."""
import json

import pytest

from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


def test_persisted_profile_requiring_unsupported_input_cannot_spawn(runtime):
    deps, client, root, peers, operator, _ = runtime
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_profiles SET config=? WHERE adapter_id='codex'",
            (json.dumps({"required_native_requests": ["item/permissions/requestApproval"]}),))
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert response.status_code == 403, response.text
    assert not peers


@pytest.mark.parametrize("adapter,requirements,expected", [
    ("codex", ["item/commandExecution/requestApproval"], 200),
    ("claude_code.stream", ["control_request:can_use_tool/Write"], 200),
    ("pi", ["item/commandExecution/requestApproval"], 422),
    ("claude_code.stream", ["control_request:can_use_tool/ExitPlanMode"], 422),
    ("codex", ["item/permissions/requestApproval"], 422),
    ("codex", "item/fileChange/requestApproval", 422),
])
def test_profile_requirements_are_validated_against_exact_adapter_contract(runtime, adapter, requirements, expected):
    _, client, _, _, operator, _ = runtime
    response = client.post("/api/v1/harness/profiles", headers={"x-api-key": operator}, json={
        "profile_id": "requirements-fixture", "adapter_id": adapter, "enabled": True,
        "config": {"required_native_requests": requirements}})
    assert response.status_code == expected, response.text


def test_required_hitl_is_rechecked_for_open_conversation_and_managed_claim(runtime, tmp_path):
    from test_pr34_remediation import send_message
    from test_runtime_handoff_dispatch import work, claim
    from test_runtime_grants import issue
    deps, client, root, peers, operator, caller = runtime
    from test_runtime_effective_requirements import install_versioned_codex
    native_peers = install_versioned_codex(runtime, tmp_path, "0.156.1")
    deps.config.feature_hitl = True
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_profiles SET config=? WHERE adapter_id='codex'",
            (json.dumps({"required_native_requests": ["item/commandExecution/requestApproval"]}),))
    args = {"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root}
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=args)
    assert opened.status_code == 200, opened.text
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work"], endpoint_id="endpoint-codex")
    deps.config.feature_hitl = False
    assert client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json=args).status_code == 403
    denied = claim(runtime, hid, grant, caller)
    assert denied.get("error", {}).get("code") == "PERMISSION_DENIED", denied
    # Disable other compatible candidates solely to observe this endpoint's
    # logical inbox fallback. The incoming message itself remains authorized.
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET enabled=0 WHERE adapter_id<>'codex'")
    sent = send_message(runtime, body="Retain inbox when required native HITL is off")
    assert not sent.get("runtime_operations")
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == "OPEN"
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?",
            (grant["grant_id"],)).fetchone()[0] == 0
    assert len(native_peers) == 1
    deps.config.feature_hitl = True
    allowed = claim(runtime, hid, grant, caller)
    assert allowed["ok"], allowed
