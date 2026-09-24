"""Kernel birth ownership and cleanup independent of stale numeric PID metadata."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

import pytest

from okto_nexus.adapters.outbound.harness.owned_process import spawn_owned_process


def environment():
    return {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}


class ExactWitness:
    """Only fixture-owned identities; emergency cleanup also avoids numeric PID."""
    def __init__(self, pid):
        if os.name == "nt":
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.kernel.OpenProcess.restype = wintypes.HANDLE
            self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel.WaitForSingleObject.restype = wintypes.DWORD
            self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = self.kernel.OpenProcess(0x100001, False, pid)
            assert self.handle
        else:
            from okto_nexus.adapters.outbound.harness.linux_process_guardian import pidfd_open
            self.handle = pidfd_open(pid)
        assert not self.stopped(0)

    def stopped(self, seconds):
        if os.name == "nt":
            return self.kernel.WaitForSingleObject(self.handle, int(seconds * 1000)) == 0
        return bool(select.select([self.handle], [], [], seconds)[0])

    def close(self):
        try:
            if not self.stopped(0):
                if os.name == "nt":
                    assert self.kernel.TerminateProcess(self.handle, 1)
                else:
                    signal.pidfd_send_signal(self.handle, signal.SIGKILL)
                assert self.stopped(5)
        finally:
            if os.name == "nt":
                self.kernel.CloseHandle(self.handle)
            else:
                os.close(self.handle)


@pytest.mark.parametrize("cut", ["before_registration", "after_registration"])
def test_owner_death_at_birth_registration_boundary_reaps_exact_tree(tmp_path, cut):
    ready = tmp_path / "ready.json"
    repo = Path(__file__).resolve().parents[1]
    env = environment() | {"PYTHONPATH": str(repo / "src"), "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    witnesses = []
    with (tmp_path / "owner.log").open("w", encoding="utf-8") as log:
        owner = subprocess.Popen([sys._base_executable, str(repo / "tests/runtime_birth_window_fixture.py"),
            str(ready), cut], stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 20
            while not ready.exists() and time.monotonic() < deadline:
                assert owner.poll() is None, (tmp_path / "owner.log").read_text(encoding="utf-8")
                time.sleep(.02)
            assert ready.exists(), (tmp_path / "owner.log").read_text(encoding="utf-8")
            marker = json.loads(ready.read_text(encoding="utf-8"))
            assert marker["owner_pid"] == owner.pid  # Never kill only a venv launcher.
            assert marker["registered"] == (1 if cut == "after_registration" else 0)
            for pid in dict.fromkeys(marker[key] for key in ("native_pid", "grand_pid", "owned_pid")):
                witnesses.append(ExactWitness(pid))
            owner.kill()
            assert owner.wait(timeout=10) != 0
            assert all(witness.stopped(5) for witness in witnesses)
        finally:
            if owner.poll() is None:
                owner.kill()
                owner.wait(timeout=10)
            owner.stdin.close()
            for witness in witnesses:
                witness.close()


@pytest.mark.parametrize("action", ["terminate", "kill"])
def test_cleanup_uses_owned_identity_when_numeric_pid_points_at_bystander(action):
    peer_code = 'import os,time; print(os.getpid(),flush=True); time.sleep(30)'
    echo_code = 'import sys; print("ready",flush=True)\nfor line in sys.stdin: print(line.strip(),flush=True)'
    pipes = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment())
    bystander = subprocess.Popen([sys._base_executable, "-u", "-c", echo_code], **pipes,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    owned, witness = None, None
    try:
        assert bystander.stdout.readline().strip() == "ready"
        owned = spawn_owned_process([sys._base_executable, "-u", "-c", peer_code], **pipes)
        witness = ExactWitness(int(owned.stdout.readline().strip()))
        original = owned.pid
        try:
            owned.pid = bystander.pid  # Simulated stale/reused numeric metadata.
            getattr(owned, action)()
        finally:
            owned.pid = original  # Popen wait still owns its real child/guardian.
        assert owned.wait(timeout=10) != 0
        assert witness.stopped(5)
        assert getattr(owned, "tree_stopped", True)
        assert bystander.poll() is None
        bystander.stdin.write("bystander survived\n")
        bystander.stdin.flush()
        assert bystander.stdout.readline().strip() == "bystander survived"
    finally:
        if owned:
            owned.kill()
            owned.wait(timeout=10)
            for stream in (owned.stdin, owned.stdout, owned.stderr):
                stream.close()
        if witness:
            witness.close()
        if bystander.poll() is None:
            bystander.terminate()
            bystander.wait(timeout=10)
        for stream in (bystander.stdin, bystander.stdout, bystander.stderr):
            stream.close()
