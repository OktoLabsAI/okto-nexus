"""Actual owner death after message commit and before notification/wake."""
import json
import time

import httpx

from test_pr34_remediation import tool
from test_runtime_relay_process_restart import Owner, PeerWitness, native_records


def test_committed_message_survives_owner_death_before_wake_without_duplicate_effect(tmp_path):
    root, home = tmp_path / "project", tmp_path / "home"
    root.mkdir()
    first, recovered, witness = Owner(home, root, "message_commit", 0), None, None
    try:
        headers = {"x-api-key": first.ready["operator"]}
        response = first.client.post("/api/v1/harness/profiles", headers=headers,
            json={"profile_id": "fixture-codex", "adapter_id": "codex", "enabled": True})
        assert response.status_code == 200, response.text
        response = first.client.post("/api/v1/harness/endpoints", headers=headers, json={
            "endpoint_id": "worker", "agent_id": "worker", "adapter_id": "codex", "project_root": str(root),
            "profile_id": "fixture-codex", "enabled": True, "response_policy": "conversation"})
        assert response.status_code == 200, response.text
        try:
            tool(first.client, first.ready["caller"], "message_create", {"project_root": str(root),
                "from_agent_id": "caller", "target": {"strategy": "direct", "agent_id": "worker"},
                "subject": "committed fixture", "body": "survive-before-wake"})
        except (httpx.RemoteProtocolError, httpx.ReadError):
            pass  # Never resend after losing an admission reply.
        assert first.process.wait(timeout=15) == 76, first.log_path.read_text(encoding="utf-8")
        assert json.loads((home / "commit-before-wake.json").read_text()) == {
            "messages": 1, "message_deliveries": 1, "delivery_outbox": 1}
        before = first.rows("SELECT * FROM delivery_outbox")[0]
        assert before["status"] == "PENDING" and before["attempt_id"] is None
        assert not native_records(home)
        recovered = Owner(home, root, "none", 600)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            operations = recovered.rows("SELECT * FROM delivery_outbox")
            if len(operations) == 1 and operations[0]["terminal_event_id"]:
                break
            time.sleep(.02)
        assert len(operations) == 1 and operations[0]["terminal_event_id"], operations
        assert operations[0]["operation_id"] == before["operation_id"]
        assert operations[0]["status"] == "ACCEPTED"
        assert recovered.rows("SELECT count(*) AS n FROM message_deliveries WHERE message_id=?", (before["message_id"],))[0]["n"] == 1
        writes = [r for r in native_records(home) if "fixture_operation" in r]
        assert [r["fixture_operation"] for r in writes] == [before["operation_id"]]
        assert recovered.rows("PRAGMA foreign_key_check") == []
        pids = [r["fixture_pid"] for r in native_records(home) if "fixture_pid" in r]
        assert len(pids) == 1
        witness = PeerWitness(pids[0])
        recovered.close()
        recovered = None
        witness.assert_stopped()
    finally:
        if recovered:
            recovered.close()
        first.close()
        if witness:
            witness.close()
