"""Two real server processes cannot concurrently own one disposable store."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from test_pr34_remediation import tool
from test_runtime_relay_process_restart import Owner, native_records


def test_second_server_process_cannot_take_live_owner_or_dispatch(tmp_path):
    root, home = tmp_path / "project", tmp_path / "home"
    root.mkdir()
    first = Owner(home, root, "none", 0)
    try:
        before = first.rows("SELECT owner_id,epoch FROM runtime_dispatcher_owner")[0]
        repo = Path(__file__).resolve().parents[1]
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        env.update(PYTHONPATH=os.pathsep.join([str(repo / "src"), str(repo / "tests")]),
                   HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8")
        ready = home / "contender-ready.json"
        contender = subprocess.run([sys.executable, str(repo / "tests/runtime_relay_process_fixture.py"),
            str(home), str(root), str(ready), "contender", "0"], env=env, cwd=root,
            input="", capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        assert "Another runtime owner" in contender.stderr, contender.stderr
        assert not ready.exists(), "failed owner exposed a ready serving app"
        assert first.process.poll() is None
        assert first.rows("SELECT owner_id,epoch FROM runtime_dispatcher_owner")[0] == before
        assert native_records(home) == []

        # Positive control: the surviving owner remains usable, with one actual
        # owned protocol process and one observed turn for this logical input.
        headers = {"x-api-key": first.ready["operator"]}
        response = first.client.post("/api/v1/harness/profiles", headers=headers,
            json={"profile_id": "fixture-codex", "adapter_id": "codex", "enabled": True})
        assert response.status_code == 200, response.text
        response = first.client.post("/api/v1/harness/endpoints", headers=headers, json={
            "endpoint_id": "worker", "agent_id": "worker", "adapter_id": "codex",
            "project_root": str(root), "profile_id": "fixture-codex", "enabled": True,
            "response_policy": "conversation"})
        assert response.status_code == 200, response.text
        sent = tool(first.client, first.ready["caller"], "message_create", {
            "project_root": str(root), "from_agent_id": "caller",
            "target": {"strategy": "direct", "agent_id": "worker"},
            "body": "one surviving owner", "subject": "owner contention"})
        assert sent["ok"], sent
        operation = sent["data"]["runtime_operations"][0]
        deadline = time.monotonic() + 10
        results = []
        while time.monotonic() < deadline:
            results = first.rows("SELECT * FROM runtime_results WHERE operation_id=?", (operation,))
            if results:
                break
            time.sleep(.02)
        assert len(results) == 1 and "one surviving owner" in results[0]["output_text"]
        records = native_records(home)
        assert len([r for r in records if "fixture_pid" in r]) == 1
        assert [r["fixture_operation"] for r in records if "fixture_operation" in r] == [operation]
        assert first.rows("SELECT owner_id,epoch FROM runtime_dispatcher_owner")[0] == before
        rows = first.rows("SELECT * FROM delivery_outbox")
        assert len(rows) == 1 and rows[0]["owner_epoch"] == before["epoch"]
        assert json.loads(rows[0]["envelope"])["operation_id"] == operation
        assert first.rows("PRAGMA foreign_key_check") == []
    finally:
        first.close()
