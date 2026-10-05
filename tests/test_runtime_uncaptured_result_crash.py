"""No invented completion/replay when native output never reached the journal."""
import json
import time

import httpx
import pytest

from test_pr34_remediation import tool
from test_runtime_relay_process_restart import Owner, PeerWitness, native_records


@pytest.mark.parametrize("cut", ["before_output_capture", "before_terminal_capture"])
def test_owner_death_before_durable_capture_leaves_detectable_unknown(tmp_path, cut):
    root, home = tmp_path / "project", tmp_path / "home"
    root.mkdir()
    first, recovered, witness = Owner(home, root, cut, 0), None, None
    try:
        headers = {"x-api-key": first.ready["operator"]}
        response = first.client.post("/api/v1/harness/profiles", headers=headers,
            json={"profile_id": "fixture-codex", "adapter_id": "codex", "enabled": True})
        assert response.status_code == 200, response.text
        response = first.client.post("/api/v1/harness/endpoints", headers=headers, json={
            "endpoint_id": "worker", "agent_id": "worker", "adapter_id": "codex", "project_root": str(root),
            "profile_id": "fixture-codex", "enabled": True, "response_policy": "conversation"})
        assert response.status_code == 200, response.text
        response = first.client.post("/api/v1/harness/sessions", headers=headers, json={
            "agent_id": "worker", "kind": "codex", "endpoint_id": "worker", "project_root": str(root)})
        assert response.status_code == 200, response.text
        pids = [r["fixture_pid"] for r in native_records(home) if "fixture_pid" in r]
        assert len(pids) == 1
        witness = PeerWitness(pids[0])
        try:
            admitted = tool(first.client, first.ready["caller"], "message_create", {
                "project_root": str(root), "from_agent_id": "caller", "subject": "uncaptured result",
                "body": "native output can be lost before capture",
                "target": {"strategy": "direct", "agent_id": "worker"}})
            assert admitted["ok"], admitted
        except (httpx.RemoteProtocolError, httpx.ReadError):
            pass  # Never resend a request after an uncertain admission response.
        assert first.process.wait(timeout=15) == 78
        witness.assert_stopped()
        marker = json.loads((home / "uncaptured-event.json").read_text(encoding="utf-8"))
        op = marker["operation_id"]
        assert marker["attempt_id"] and marker["watermark"] > 0
        assert (marker["kind"] == "output_delta" if cut == "before_output_capture" else marker["phase"] == "terminal")
        recovered = Owner(home, root, "none", 600)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            row = recovered.rows("SELECT * FROM delivery_outbox WHERE operation_id=?", (op,))[0]
            if row["status"] == "OUTCOME_UNKNOWN":
                break
            time.sleep(.02)
        assert row["status"] == "OUTCOME_UNKNOWN" and row["terminal_event_id"] is None
        assert row["attempt_id"] == marker["attempt_id"]
        assert recovered.rows("SELECT count(*) AS n FROM runtime_results")[0]["n"] == 0
        assert recovered.rows("SELECT count(*) AS n FROM messages WHERE subject LIKE 'runtime processing receipt:%'")[0]["n"] == 0
        delivery = recovered.rows("SELECT status,consumer_kind FROM message_deliveries WHERE delivery_id=?", (row["delivery_id"],))[0]
        assert delivery == {"status": "unread", "consumer_kind": "push"}
        visible = tool(recovered.client, recovered.ready["operator"], "harness_get", {"operation_id": op})
        assert visible["ok"] and visible["data"]["state"] == "OUTCOME_UNKNOWN", visible
        assert visible["data"]["result_durable"] is False
        assert recovered.rows("SELECT health FROM agent_endpoints WHERE endpoint_id='worker'")[0]["health"] == "quarantined"
        # Wait for acknowledged API reads across explicit wakes, not a blind
        # sleep or a fabricated successful native completion.
        for _ in range(3):
            recovered.process.stdin.write("wake\n")
            recovered.process.stdin.flush()
            assert tool(recovered.client, recovered.ready["operator"], "harness_get", {"operation_id": op})["data"]["state"] == "OUTCOME_UNKNOWN"
        assert [r["fixture_operation"] for r in native_records(home) if "fixture_operation" in r] == [op]
        assert len([r for r in native_records(home) if "fixture_pid" in r]) == 1
        assert recovered.rows("PRAGMA foreign_key_check") == []
    finally:
        if recovered:
            recovered.close()
        first.close()
        if witness:
            witness.close()
