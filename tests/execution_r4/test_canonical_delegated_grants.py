"""Delegated actors keep endpoint/action ceilings across public transports."""
import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_agent_recovery_isolation import create_agent
from test_canonical_grant_regressions import mcp_helpers


def delegated(connected, actions, budget=2):
    from okto_nexus.domain.base import iso_plus
    setup, binding, native = connected
    caller = create_agent(setup, "caller")
    setup[3]["caller"] = caller[3]["subject"]
    setup[2].headers["host"] = "127.0.0.1:8000"
    opened = admit(setup, binding, "delegated-open", "runtime.start", new_session=True)
    wait_receipt(setup, opened)
    response = setup[2].post("/api/v1/harness/grants", headers=setup[3]["operator"], json=dict(
        actor_agent_id="caller", endpoint_id=binding["endpoint_id"], actions=actions,
        max_executions=budget, expires_at=iso_plus(setup[0].clock.now_iso(), 600)))
    assert response.status_code == 200, response.text
    return setup, binding, native, opened["scope"]["session_id"], response.json()["data"]


def tool_call(setup, name, **kwargs):
    from test_pr34_remediation import tool
    return tool(setup[2], setup[3]["caller"]["Authorization"].removeprefix("Bearer "), name, kwargs)


@pytest.mark.parametrize("actions", [["read"], ["read", "send"], ["open"]])
def test_ordinary_endpoint_grant_cannot_represent_another_core_identity(connected_local, actions):
    # M04_OPERATOR_RUNTIME makes represented R4 execution operator-only;
    # a legacy endpoint grant does not mint that operator identity.
    setup, binding, native, sid, _ = delegated(connected_local, actions)
    known = tool_call(setup, "harness_get", session_id=sid)
    absent = tool_call(setup, "harness_get", session_id="missing-private-session")
    assert known == absent and known["error"]["code"] == "PERMISSION_DENIED"
    body = dict(payload=dict(text="Foreign delegated control"), idempotency_key="foreign-command")
    sent = tool_call(setup, "harness_send", session_id=sid, **body)
    rest = setup[2].post(f"/api/v1/harness/sessions/{sid}/send", headers=setup[3]["caller"], json=body)
    assert not sent["ok"] and rest.status_code in (403, 404)
    opened = tool_call(setup, "harness_open", agent_id="subject", kind="codex", project_root=str(setup[-1]),
        endpoint_id=binding["endpoint_id"], idempotency_key="foreign-opening")
    assert not opened["ok"] and opened["error"]["code"] == "PERMISSION_DENIED"
    assert native.opens == 1 and not native.native.sent






@pytest.mark.parametrize("change", ["permissions", "scope", "credential", "profile"])
def test_delegated_authority_changes_are_rechecked_on_both_transports(connected_local, change):
    setup, binding, native, sid, grant = delegated(connected_local, ["read", "send"])
    from okto_nexus.bootstrap.execution_authority import build_execution_access
    from okto_nexus.domain.runtime_context import RuntimeRequestContext
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        credential = uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='caller'").fetchone()[0]
    context = RuntimeRequestContext("caller", "agent_key", credential_binding=credential)
    # Separate endpoint policy from R4's additional identity boundary.
    build_execution_access(setup[0]).authorize(context, action="send", endpoint_id=binding["endpoint_id"])
    with setup[0].connection_factory.unit_of_work() as uow:
        if change == "permissions":
            uow.connection.execute("UPDATE agents SET permissions=? WHERE agent_id='caller'", ('{"messages":{"send_direct":false}}',))
        elif change == "scope":
            uow.connection.execute("UPDATE agents SET comm_scope=? WHERE agent_id='caller'", ('{"outbound":{"team":["elsewhere"]}}',))
        elif change == "credential":
            uow.connection.execute("UPDATE runtime_execution_grants SET credential_binding='other' WHERE grant_id=?", (grant["grant_id"],))
        else:
            uow.connection.execute("UPDATE runtime_profiles SET revision=revision+1 WHERE profile_id=(SELECT profile_id FROM agent_endpoints WHERE endpoint_id=?)", (binding["endpoint_id"],))
    from okto_nexus.errors import OktoNexusError
    with pytest.raises(OktoNexusError):
        build_execution_access(setup[0]).authorize(context, action="send", endpoint_id=binding["endpoint_id"])
    body = dict(payload=dict(text="Denied changed authority"), idempotency_key="changed-authority")
    denied = tool_call(setup, "harness_send", session_id=sid, **body)
    rest = setup[2].post(f"/api/v1/harness/sessions/{sid}/send", headers=setup[3]["caller"], json=body)
    assert not denied["ok"] and rest.status_code in (403, 409), (denied, rest.text)
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_access_audit WHERE decision='deny'").fetchone()[0] >= 2
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 0
    assert not native.native.sent


def test_operator_cannot_control_session_after_approved_profile_changes(connected_local):
    from test_operator_runtime import resolve, submit
    setup, binding, native = connected_local
    response = resolve(setup, binding, new_session=True)
    assert response.status_code == 200, response.text
    opened = response.json()
    assert submit(setup, opened).status_code == 202
    wait_receipt(setup, opened)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_profiles SET revision=revision+1 WHERE profile_id=(SELECT profile_id FROM agent_endpoints WHERE endpoint_id=?)", (binding["endpoint_id"],))
    refused = resolve(setup, binding, intent_id="changed-profile", intent="turn.submit",
                      session_id=opened["session_id"], text="Must not reach the harness")
    if refused.status_code == 200:
        operation = refused.json()
        refused = submit(setup, operation)
        if refused.status_code == 202:
            from test_agent_recovery_isolation import eventually
            def dispatch_refused():
                with setup[0].connection_factory.unit_of_work(write=False) as uow:
                    row = uow.connection.execute("SELECT dispatch_state,last_error FROM execution_dispatch_outbox WHERE operation_id=?", (operation["operation_id"],)).fetchone()
                    if row and row[0] == "RESOLVED_TERMINAL":
                        import json
                        error = json.loads(row[1])
                        assert error["code"] in ("PERMISSION_DENIED", "CONFLICT")
                        assert error["possible_effect"] is False
                        return True
                    return False
            eventually(dispatch_refused)
        else:
            assert refused.status_code in (403, 409), refused.text
    else:
        assert refused.status_code in (403, 409), refused.text
    assert native.opens == 1 and not native.native.sent
