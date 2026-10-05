"""Revocation after native acceptance preserves evidence without work authority."""
from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation
from test_runtime_grants import issue
from test_runtime_handoff_dispatch import work, wait_result
from test_runtime_work_results import native_work_peer, outcome, state

runtime = runtime_fixture


def test_revoke_accepted_turn_before_terminal_keeps_evidence_and_blocks_completion(runtime, tmp_path):
    deps, client, root, _, operator, caller = runtime
    release = tmp_path / "release-native-terminal"
    mutation = ("deadline = time.monotonic() + 15\n"
        f"    while not os.path.exists({str(release)!r}):\n"
        "        assert time.monotonic() < deadline, 'fixture release deadline'\n"
        "        time.sleep(.01)")
    native_work_peer(runtime, mutation=mutation)
    hid, _ = work(runtime)
    grant = issue(runtime, ["execute_work", "read", "send"], endpoint_id="endpoint-codex")
    admitted = tool(client, caller, "handoff_claim", {"project_root": root, "handoff_id": hid,
        "agent_id": "worker", "runtime_endpoint_id": "endpoint-codex",
        "execution_grant_id": grant["grant_id"], "idempotency_key": "revoke-active-work",
        "completion_mode": "structured_result_v1"})
    assert admitted["ok"], admitted
    op = admitted["data"]["runtime_operation"]["operation_id"]
    try:
        accepted = wait_operation(runtime, op, lambda row: row["ack_level"] == "HARNESS_ACCEPTED")
        assert not accepted["result_durable"] and accepted["result"] is None
        assert tool(client, caller, "harness_get", {"operation_id": op})["ok"]
        assert client.delete("/api/v1/harness/grants/" + grant["grant_id"], headers={"x-api-key": operator}).status_code == 200
        sid = accepted["session_id"]
        denied = tool(client, caller, "harness_send", {"session_id": sid, "payload": {"text": "never sent"}})
        rest = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": caller},
            json={"payload": {"text": "never sent"}})
        assert not denied["ok"] and denied["error"]["code"] == "PERMISSION_DENIED"
        assert rest.status_code == 403
        assert not tool(client, caller, "harness_get", {"operation_id": op})["ok"]
    finally:
        release.write_text("release", encoding="utf-8")
    assert outcome(runtime, op)["state"] == "BLOCKED"
    assert state(runtime, hid, "CLAIMED")["result"] is None
    historical = wait_result(runtime, op)
    assert "fixture evidence" in historical["output_text"]
    assert not historical["publication_message_id"]
    persisted = wait_operation(runtime, op, lambda row: row["result_durable"])
    assert persisted["ack_level"] == "HARNESS_ACCEPTED"
    assert persisted["work_outcome"]["state"] == "BLOCKED"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert not uow.connection.execute("SELECT 1 FROM runtime_commands").fetchone()
        assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE operation_id=?", (op,)).fetchone()[0] == 1
