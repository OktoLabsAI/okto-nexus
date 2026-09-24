"""Real owner death after atomic projection/checkpoint commit, before publication."""
from contextlib import closing
import json
import sqlite3
import time

import httpx
import pytest

from test_pr34_remediation import tool
from test_runtime_relay_process_restart import Owner, PeerWitness, native_records


@pytest.mark.parametrize("rewind_checkpoint", [False, True])
def test_committed_projection_survives_owner_death_and_replay_once(tmp_path, rewind_checkpoint):
    root, home = tmp_path / "project", tmp_path / "home"
    root.mkdir()
    first, recovered, witness = Owner(home, root, "projection_commit", 0), None, None
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
        processes = [row["fixture_pid"] for row in native_records(home) if "fixture_pid" in row]
        assert len(processes) == 1
        witness = PeerWitness(processes[0])
        try:
            admitted = tool(first.client, first.ready["caller"], "message_create", {
                "project_root": str(root), "from_agent_id": "caller", "subject": "committed projection",
                "body": "one durable terminal", "target": {"strategy": "direct", "agent_id": "worker"}})
            assert admitted["ok"], admitted
        except (httpx.RemoteProtocolError, httpx.ReadError):
            pass  # A lost response never authorizes sending the message again.
        assert first.process.wait(timeout=15) == 77
        witness.assert_stopped()
        marker = json.loads((home / "projection-committed.json").read_text(encoding="utf-8"))
        op, event = marker["operation_id"], marker["event_id"]
        assert marker["checkpoint"] > 0
        assert marker["receipt_count"] == 1 and marker["delivery_status"] == "read"
        before = first.rows("SELECT * FROM runtime_results WHERE operation_id=?", (op,))
        assert len(before) == 1 and before[0]["publication_message_id"] is None
        assert before[0]["event_id"] == event and "one durable terminal" in before[0]["output_text"]
        assert first.rows("SELECT ordinal FROM runtime_journal_checkpoint")[0]["ordinal"] == marker["checkpoint"]
        if rewind_checkpoint:
            # Stronger replay stimulus on this disposable, stopped store. Normal
            # production commit cannot split its SQLite projection/checkpoint.
            with closing(sqlite3.connect(home / "nexus.db")) as connection:
                connection.execute("UPDATE runtime_journal_checkpoint SET ordinal=0")
                connection.commit()
        recovered = Owner(home, root, "none", 600)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            results = recovered.rows("SELECT * FROM runtime_results WHERE operation_id=?", (op,))
            if len(results) == 1 and results[0]["publication_state"] == "PUBLISHED":
                break
            time.sleep(.02)
        assert len(results) == 1 and results[0]["publication_state"] == "PUBLISHED"
        assert results[0]["result_id"] == before[0]["result_id"]
        assert results[0]["event_id"] == event and results[0]["attempt_id"] == before[0]["attempt_id"]
        assert results[0]["output_text"] == before[0]["output_text"]
        assert recovered.rows("SELECT count(*) AS n FROM runtime_results")[0]["n"] == 1
        assert recovered.rows("SELECT count(*) AS n FROM harness_events WHERE event_id=?", (event,))[0]["n"] == 1
        assert recovered.rows("SELECT count(*) AS n FROM messages WHERE subject LIKE 'runtime processing receipt:%'")[0]["n"] == 1
        assert recovered.rows("SELECT count(*) AS n FROM messages WHERE subject='Runtime result'")[0]["n"] == 1
        operations = recovered.rows("SELECT operation_id,terminal_event_id,status FROM delivery_outbox")
        assert operations == [{"operation_id": op, "terminal_event_id": event, "status": "ACCEPTED"}]
        writes = [row["fixture_operation"] for row in native_records(home) if "fixture_operation" in row]
        assert writes == [op]
        assert len([row for row in native_records(home) if "fixture_pid" in row]) == 1
        assert recovered.rows("SELECT ordinal FROM runtime_journal_checkpoint")[0]["ordinal"] >= marker["checkpoint"]
        assert recovered.rows("PRAGMA foreign_key_check") == []
    finally:
        if recovered:
            recovered.close()
        first.close()
        if witness:
            witness.close()
