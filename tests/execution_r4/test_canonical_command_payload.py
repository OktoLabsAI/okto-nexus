"""R4 direct commands accept text; execution identity comes from authorization."""
import json

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_canonical_grant_regressions import mcp_helpers, invoke_command, open_scoped


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_direct_command_refuses_legacy_envelopes_and_payload_authority(connected_local, monkeypatch, transport):
    setup, _, native, _, session = open_scoped(connected_local)
    canonical = dict(schema_version=1, content=[dict(type="text", text="untrusted")])
    invalid = ["{", "[]", dict(text="different", content="conflicting"), canonical,
        dict(canonical, schema_version=True), dict(canonical, schema_version=2),
        dict(canonical, content=[]), dict(canonical, content=[dict(type="image", text="no")]),
        dict(canonical, response_requested="true"), dict(canonical, intent="handoff_execute"),
        dict(canonical, subject=42)]
    fields = dict(sender_agent_id="operator", recipient_agent_id="foreign", workspace_id="other",
        operation_id="forged", root_operation_id="forged", trust="system", handoff_id="forged",
        claim_epoch=1, runtime_context={}, native_options={}, artifact_refs=["private-artifact"])
    invalid.extend(dict(text="input", **{key: value}) for key, value in fields.items())
    for payload in invalid:
        denied = invoke_command(setup, monkeypatch, transport, session,
            dict(idempotency_key="strict-payload", payload=payload))
        assert not denied["ok"] and denied["error"]["code"] == "VALIDATION_ERROR", (payload, denied)
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 0
    assert not native.native.sent
    body = dict(idempotency_key="strict-payload", payload=dict(text="Authorized ordinary text"))
    first = invoke_command(setup, monkeypatch, transport, session, body)
    assert first["ok"], first
    wait_receipt(setup, first["data"])
    replay = invoke_command(setup, monkeypatch, "mcp" if transport == "rest" else "rest", session, body)
    assert replay["ok"] and replay["data"]["operation_id"] == first["data"]["operation_id"], replay
    for payload in (dict(content=body["payload"]["text"]), dict(body["payload"], content=body["payload"]["text"]),
                    json.dumps(body["payload"])):
        normalized = invoke_command(setup, monkeypatch, transport, session, dict(body, payload=payload))
        assert normalized["ok"] and normalized["data"]["operation_id"] == first["data"]["operation_id"], normalized
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT actor_agent_id,subject_agent_id,semantic_payload FROM execution_operations WHERE action='turn.submit'").fetchone()
        assert row[:2] == ("subject", "subject")
        assert "Authorized ordinary text" in row[2]
        assert uow.connection.execute("SELECT COUNT(*) FROM runtime_commands").fetchone()[0] == 0
    assert len(native.native.sent) == 1


def test_launch_overrides_cannot_replace_approved_realization_on_either_surface(connected_local):
    from test_pr34_remediation import tool
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    client.headers["host"] = "127.0.0.1:8000"
    key = headers["subject"]["Authorization"].removeprefix("Bearer ")
    overrides = dict(cwd="unapproved", sandbox="danger-full-access", provider="unapproved",
        env={"FIXTURE_ONLY": "unapproved"}, argv=["unapproved"])
    for field, value in overrides.items():
        args = dict(agent_id="subject", kind="codex", endpoint_id=binding["endpoint_id"],
            project_root=str(root), idempotency_key="no-launch-override", backend={field: value})
        mcp = tool(client, key, "harness_open", args)
        rest = client.post("/api/v1/harness/sessions", headers=headers["subject"], json=args)
        assert mcp["error"]["code"] == "VALIDATION_ERROR", mcp
        assert rest.status_code == 422, rest.text
    assert native.opens == 0
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 0


@pytest.mark.parametrize("verb", ["send", "steer", "interrupt"])
def test_control_payload_cannot_replace_identity_or_native_configuration(connected_local, verb):
    from test_pr34_remediation import tool
    setup, _, native, _, sid = open_scoped(connected_local)
    deps, _, client, headers, *_, root = setup
    key = headers["subject"]["Authorization"].removeprefix("Bearer ")
    fields = dict(actor_agent_id="operator", from_agent_id="operator", grant_id="forged",
        root_operation_id="forged", cwd=str(root) + "-other", sandbox="danger-full-access",
        provider="unapproved", env={"FIXTURE_ONLY": "unapproved"}, argv=["unapproved"])
    for field, value in fields.items():
        body = dict(idempotency_key="no-control-override", payload={"text": "must not execute", field: value})
        if verb == "steer":
            body["expected_turn_id"] = "turn-from-native"
        mcp = tool(client, key, "harness_" + verb, dict(session_id=sid, **body))
        rest = client.post(f"/api/v1/harness/sessions/{sid}/{verb}", headers=headers["subject"], json=body)
        assert mcp["error"]["code"] == "VALIDATION_ERROR", (field, mcp)
        assert rest.status_code == 422, (field, rest.text)
    assert native.opens == 1 and not native.native.sent
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
