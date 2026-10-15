"""Cached commands retain current execution authorization and shutdown fences."""
import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt
from test_canonical_grant_regressions import mcp_helpers, open_scoped, invoke_command


@pytest.mark.parametrize("verb", ["send", "steer", "interrupt", "close"])
def test_revocation_denies_cached_control_without_repeating_native_effect(connected_local, monkeypatch, verb):
    from test_pr34_remediation import tool
    setup, _, native, grant, sid = open_scoped(connected_local)
    deps, _, client, headers, *_ = setup
    key = headers["subject"]["Authorization"].removeprefix("Bearer ")
    if verb in ("steer", "interrupt"):
        sent = invoke_command(setup, monkeypatch, "rest", sid,
            dict(payload=dict(text="Active turn"), idempotency_key="active-before-control"))
        assert sent["ok"], sent
        wait_receipt(setup, sent["data"])
    body = dict(idempotency_key="cached-" + verb)
    if verb in ("send", "steer"):
        body["payload"] = dict(text="Authorized control")
    if verb == "steer":
        body["expected_turn_id"] = "turn-from-native"
    original = tool(client, key, "harness_" + verb, dict(session_id=sid, **body))
    assert original["ok"], original
    wait_receipt(setup, original["data"])
    path = f"/api/v1/harness/sessions/{sid}/{verb}"
    replay = client.post(path, headers=headers["subject"], json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["operation_id"] == original["data"]["operation_id"]
    before = list(native.native.sent)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        count = uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0]
    revoked = client.delete("/api/v1/harness/grants/" + grant["grant_id"], headers=headers["operator"])
    assert revoked.status_code == 200, revoked.text
    denied = tool(client, key, "harness_" + verb, dict(session_id=sid, **body))
    response = client.post(path, headers=headers["subject"], json=body)
    assert response.status_code == 403, response.text
    assert denied["error"]["code"] == "PERMISSION_DENIED", denied
    assert native.native.sent == before
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == count
    # R4 historical receipts remain available to their authenticated subject;
    # revoking execution consent never erases the evidence of the old effect.
    history = client.get("/v1/runtime/operations/" + original["data"]["operation_id"], headers=headers["subject"])
    assert history.status_code == 200, history.text


@pytest.mark.parametrize("surface", ["rest", "mcp"])
def test_shutdown_fence_refuses_new_compatibility_turn_but_allows_close(connected_local, monkeypatch, surface):
    from test_pr34_remediation import tool
    setup, _, native, _, sid = open_scoped(connected_local)
    deps, _, client, headers, *_ = setup
    deps.runtime_admission_fence.close()
    denied = invoke_command(setup, monkeypatch, surface, sid,
        dict(payload=dict(text="Do not execute"), idempotency_key="shutdown-denied"))
    assert denied["error"]["code"] == "CONFLICT", denied
    assert native.native.sent == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM execution_operations").fetchone()[0] == 1
    closed = tool(client, headers["subject"]["Authorization"].removeprefix("Bearer "),
        "harness_close", dict(session_id=sid, idempotency_key="shutdown-close"))
    assert closed["ok"], closed
    wait_receipt(setup, closed["data"], stages=("SUCCEEDED",))
    assert native.opens == 1 and native.native.stopped
