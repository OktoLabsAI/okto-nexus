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
            from legacy_native_fixture.linux_process_guardian import pidfd_open
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
