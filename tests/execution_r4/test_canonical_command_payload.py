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
