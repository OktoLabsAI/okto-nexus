"""Expired SENDING after actual acceptance remains unknown and never replays."""
import json
import time

import httpx

from test_pr34_remediation import tool
from test_runtime_relay_process_restart import Owner, PeerWitness, native_records


def test_owner_crash_after_wire_acceptance_with_sending_lease_never_replays(tmp_path):
    root, home = tmp_path / "project", tmp_path / "home"
    root.mkdir()
    first = Owner(home, root, "sending_accepted", 0)
    recovered, witness = None, None
    try:
        headers = {"x-api-key": first.ready["operator"]}
        response = first.client.post("/api/v1/harness/profiles", headers=headers,
            json={"profile_id": "fixture-codex", "adapter_id": "codex", "enabled": True})
        assert response.status_code == 200, response.text
        response = first.client.post("/api/v1/harness/endpoints", headers=headers, json={
            "endpoint_id": "worker", "agent_id": "worker", "adapter_id": "codex",
            "project_root": str(root), "profile_id": "fixture-codex", "enabled": True,
            "response_policy": "conversation"})
        assert response.status_code == 200, response.text
        response = first.client.post("/api/v1/harness/sessions", headers=headers, json={
            "agent_id": "worker", "kind": "codex", "endpoint_id": "worker", "project_root": str(root)})
        assert response.status_code == 200, response.text
        witness = PeerWitness(next(r["fixture_pid"] for r in native_records(home) if "fixture_pid" in r))
        try:
            response = tool(first.client, first.ready["caller"], "message_create", {
                "project_root": str(root), "from_agent_id": "caller",
                "target": {"strategy": "direct", "agent_id": "worker"},
                "subject": "ambiguous SENDING", "body": "TRIGGER_HOLD"})
            assert response["ok"], response
        except (httpx.RemoteProtocolError, httpx.ReadError):
            pass  # A lost response never authorizes resubmission.
        assert first.process.wait(timeout=15) == 79, first.log_path.read_text(encoding="utf-8")
        witness.assert_stopped()
        marker = json.loads((home / "sending-accepted.json").read_text())
        operation = marker["operation_id"]
        assert marker["status"] == "SENDING" and marker["lease_expires_at"]
        assert first.rows("SELECT status FROM delivery_outbox")[0]["status"] == "SENDING"
        assert first.rows("SELECT * FROM runtime_results") == []

        # Only the application's test clock advances; persisted leases and host
        # time are not rewritten. The new production owner performs recovery.
        recovered = Owner(home, root, "none", 600)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            row = recovered.rows("SELECT * FROM delivery_outbox")[0]
            if row["status"] == "OUTCOME_UNKNOWN":
                break
            time.sleep(.02)
        assert row["status"] == "OUTCOME_UNKNOWN"
        assert row["operation_id"] == operation and row["attempt_id"] == marker["attempt_id"]
        assert row["attempt_count"] == 1 and not row["terminal_event_id"]
        assert recovered.rows("SELECT epoch FROM runtime_dispatcher_owner")[0]["epoch"] > marker["owner_epoch"]
        assert recovered.rows("SELECT health FROM agent_endpoints WHERE endpoint_id='worker'")[0]["health"] == "quarantined"
        for _ in range(3):
            recovered.process.stdin.write("wake\n")
            recovered.process.stdin.flush()
            inspected = tool(recovered.client, recovered.ready["operator"], "harness_get", {"operation_id": operation})
            assert inspected["ok"] and not inspected["data"]["result_durable"], inspected
        assert recovered.rows("SELECT * FROM runtime_results") == []
        delivery = recovered.rows("SELECT status,consumer_kind,consumer_operation_id,attempts FROM message_deliveries")[0]
        assert delivery == {"status": "unread", "consumer_kind": "push", "consumer_operation_id": operation, "attempts": 0}
        records = native_records(home)
        assert len([r for r in records if "fixture_pid" in r]) == 1
        assert [r["fixture_operation"] for r in records if "fixture_operation" in r] == [operation]
        assert recovered.rows("PRAGMA foreign_key_check") == []
    finally:
        if recovered:
            recovered.close()
        first.close()
        if witness:
            witness.close()
