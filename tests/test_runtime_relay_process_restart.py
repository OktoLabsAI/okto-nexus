"""Crash actual HTTP owners and recover durable relay without model/provider I/O."""
import ctypes
from contextlib import closing
from ctypes import wintypes
import json
import os
from pathlib import Path
import select
import sqlite3
import subprocess
import sys
import time

import httpx
import pytest

from test_pr34_remediation import tool


class Owner:
    def __init__(self, home, root, cut, offset, *, ready_timeout=20):
        self.home = home
        home.mkdir(exist_ok=True)
        ready = home / f"ready-{cut}-{offset}.json"
        self.log_path = home / f"owner-{cut}-{offset}.log"
        self.log = self.log_path.open("w", encoding="utf-8")
        repo = Path(__file__).resolve().parents[1]
        env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        env.update(PYTHONPATH=os.pathsep.join([str(repo / "src"), str(repo / "tests")]),
                   HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8")
        self.process = subprocess.Popen([sys.executable, str(repo / "tests/runtime_relay_process_fixture.py"),
            str(home), str(root), str(ready), cut, str(offset)], env=env, cwd=root,
            stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.client = None
        try:
            deadline = time.monotonic() + ready_timeout
            while not ready.exists() and time.monotonic() < deadline:
                assert self.process.poll() is None, self.log_path.read_text(encoding="utf-8")
                time.sleep(.02)
            assert ready.exists(), self.log_path.read_text(encoding="utf-8")
            self.ready = json.loads(ready.read_text(encoding="utf-8"))
            self.client = httpx.Client(base_url=self.ready["url"], timeout=10)
        except BaseException:
            self.close()
            raise

    def rows(self, sql, args=()):
        with closing(sqlite3.connect(self.home / "nexus.db", timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(sql, args)]

    def close(self):
        if self.client:
            self.client.close()
        if self.process.poll() is None:
            try:
                self.process.stdin.write("stop\n")
                self.process.stdin.flush()
                self.process.wait(timeout=15)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=10)
        self.process.stdin.close()
        self.log.close()


class PeerWitness:
    """Hold the exact disposable process identity, never signal a numeric PID."""
    def __init__(self, pid):
        if os.name == "nt":
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.kernel.OpenProcess.restype = wintypes.HANDLE
            self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel.WaitForSingleObject.restype = wintypes.DWORD
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = self.kernel.OpenProcess(0x100000, False, pid)
            assert self.handle and self.kernel.WaitForSingleObject(self.handle, 0) == 258
        else:
            from okto_nexus.adapters.outbound.harness.linux_process_guardian import pidfd_open
            self.handle = pidfd_open(pid)
            assert not select.select([self.handle], [], [], 0)[0]

    def assert_stopped(self):
        if os.name == "nt":
            assert self.kernel.WaitForSingleObject(self.handle, 5000) == 0
        else:
            assert select.select([self.handle], [], [], 5)[0]

    def close(self):
        if os.name == "nt":
            self.kernel.CloseHandle(self.handle)
        else:
            os.close(self.handle)


def native_records(home):
    return [json.loads(line) for path in home.glob("native-*.jsonl")
            for line in path.read_text(encoding="utf-8").splitlines(keepends=True) if line.endswith("\n")]


@pytest.mark.parametrize("cut,exit_code,offset", [("journal_terminal", 73, 600),
    ("journal_terminal", 73, 1800), ("committed_child", 74, 600), ("accepted_child", 75, 600)])
def test_whole_owner_crash_preserves_relay_lineage_and_never_replays_ambiguous_child(tmp_path, cut, exit_code, offset):
    root, home = tmp_path / "project", tmp_path / "home"
    root.mkdir()
    first, recovered, witnesses = Owner(home, root, cut, 0), None, []
    try:
        headers = {"x-api-key": first.ready["operator"]}
        response = first.client.post("/api/v1/harness/profiles", headers=headers,
            json={"profile_id": "fixture-codex", "adapter_id": "codex", "enabled": True})
        assert response.status_code == 200, response.text
        for agent in ("worker", "caller"):
            response = first.client.post("/api/v1/harness/endpoints", headers=headers, json={
                "endpoint_id": agent, "agent_id": agent, "adapter_id": "codex", "project_root": str(root),
                "profile_id": "fixture-codex", "enabled": True, "response_policy": "conversation",
                "public_config": {"relay_results": True}})
            assert response.status_code == 200, response.text
            if agent == "worker" or cut == "accepted_child":
                response = first.client.post("/api/v1/harness/sessions", headers=headers, json={
                    "agent_id": agent, "kind": "codex", "endpoint_id": agent, "project_root": str(root)})
                assert response.status_code == 200, response.text
        for row in native_records(home):
            if "fixture_pid" in row:
                witnesses.append(PeerWitness(row["fixture_pid"]))
        assert len(witnesses) == (2 if cut == "accepted_child" else 1)
        try:
            sent = tool(first.client, first.ready["caller"], "message_create", {"project_root": str(root),
                "from_agent_id": "caller", "target": {"strategy": "direct", "agent_id": "worker"},
                "subject": "fixture", "body": "cross-process-root"})
            assert sent["ok"], sent
        except (httpx.RemoteProtocolError, httpx.ReadError):
            pass  # Lost admission response is not permission to resend.
        assert first.process.wait(timeout=15) == exit_code, first.log_path.read_text(encoding="utf-8")
        for witness in witnesses:
            witness.assert_stopped()
        original = first.rows("SELECT * FROM runtime_causal_roots")[0]
        before = first.rows("SELECT * FROM delivery_outbox ORDER BY created_at,operation_id")
        assert len(before) == (1 if cut == "journal_terminal" else 2)
        recovered = Owner(home, root, "none", offset)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            operations = recovered.rows("SELECT * FROM delivery_outbox ORDER BY created_at,operation_id")
            results = recovered.rows("SELECT * FROM runtime_results ORDER BY captured_at,result_id")
            if offset == 1800:
                if len(results) == 1 and results[0]["publication_state"] == "PUBLISHED":
                    break
            elif cut == "accepted_child":
                if len(operations) == 2 and operations[1]["status"] == "OUTCOME_UNKNOWN":
                    break
            elif len(results) == 2 and all(r["publication_state"] == "PUBLISHED" for r in results):
                break
            time.sleep(.02)
        expected = 1 if offset == 1800 else 2
        assert len(operations) == expected, operations
        assert operations[0]["operation_id"] == before[0]["operation_id"]
        assert operations[0]["status"] == "ACCEPTED" and operations[0]["terminal_event_id"]
        if offset == 1800:
            assert len(results) == 1 and results[0]["publication_state"] == "PUBLISHED"
            assert results[0]["relay_state"] == "BLOCKED"
            assert results[0]["relay_reason"] == "QUOTA_EXCEEDED"
        elif cut == "accepted_child":
            assert operations[1]["status"] == "OUTCOME_UNKNOWN" and not operations[1]["terminal_event_id"]
            assert len(results) == 1
        else:
            assert len(results) == 2 and all(r["publication_state"] == "PUBLISHED" for r in results), results
            assert operations[1]["status"] == "ACCEPTED" and operations[1]["terminal_event_id"]
        roots = recovered.rows("SELECT * FROM runtime_causal_roots")
        assert len(roots) == 1
        assert roots[0]["root_operation_id"] == original["root_operation_id"]
        assert roots[0]["deadline"] == original["deadline"]
        assert (roots[0]["generated_messages"], roots[0]["admitted_executions"]) == (expected - 1, expected)
        assert {op["root_operation_id"] for op in operations} == {original["root_operation_id"]}
        writes = [r for r in native_records(home) if "fixture_operation" in r]
        assert [r["fixture_operation"] for r in sorted(writes, key=lambda r: r["recipient"], reverse=True)] == [op["operation_id"] for op in operations]
        assert [json.loads(op["envelope"])["hop_count"] for op in operations] == list(range(expected))
        assert recovered.rows("PRAGMA foreign_key_check") == []
    finally:
        if recovered:
            recovered.close()
        first.close()
        for witness in witnesses:
            witness.close()


def test_slow_canonical_chain_keeps_deadline_across_four_server_processes(tmp_path):
    root, home = tmp_path / "project", tmp_path / "home"
    root.mkdir()
    parent, initial, owners = None, None, []
    for offset in (0, 600, 1200, 1800):
        owner = Owner(home, root, "none", offset)
        try:
            identity = owner.rows("SELECT owner_id,epoch FROM runtime_dispatcher_owner")[0]
            owners.append(identity["owner_id"])
            arguments = {"project_root": str(root), "from_agent_id": "caller",
                "target": {"strategy": "direct", "agent_id": "worker"}, "subject": "fixture", "body": "slow continuation"}
            if parent:
                arguments["parent_message_id"] = parent
            response = tool(owner.client, owner.ready["caller"], "message_create", arguments)
            if offset == 1800:
                assert not response["ok"] and response["error"]["code"] == "QUOTA_EXCEEDED", response
            else:
                assert response["ok"], response
                parent = response["data"]["message_id"]
            root_row = owner.rows("SELECT * FROM runtime_causal_roots")[0]
            initial = initial or root_row
            assert root_row["root_operation_id"] == initial["root_operation_id"]
            assert root_row["deadline"] == initial["deadline"]
            assert root_row["max_depth"] == 4
            assert root_row["generated_messages"] == min(offset // 600, 2)
            if offset == 1800:
                del arguments["parent_message_id"]
                fresh = tool(owner.client, owner.ready["caller"], "message_create", arguments)
                assert fresh["ok"], fresh
                assert len(owner.rows("SELECT * FROM runtime_causal_roots")) == 2
            assert owner.rows("SELECT * FROM delivery_outbox") == []
        finally:
            owner.close()
        assert owner.process.returncode == 0
    assert len(set(owners)) == 4
