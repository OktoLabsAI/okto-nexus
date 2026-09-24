"""Real disposable Python processes; no model, personal account or native peer."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from okto_nexus.application.runtime_lifecycle import RuntimeLifecycle
from okto_nexus.adapters.outbound.harness.owned_process import spawn_owned_process
from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from okto_nexus.errors import OktoNexusError
from test_harness_supervisor import make_factory, make_supervisor, _Clock, FakeConnector, wait_until
from test_pr34_remediation import runtime as runtime_fixture

runtime = runtime_fixture


def fixture_environment():
    return {key: value for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}}


def spawn(argv):
    return spawn_owned_process(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", env=fixture_environment())


def test_cancel_before_spawn_has_no_effect(tmp_path):
    marker = tmp_path / "never-created"
    scope = RuntimeLifecycle()
    scope.cancel()
    with pytest.raises(RuntimeError, match="cancelled"), scope.activate():
        spawn([sys.executable, "-c", f"open({str(marker)!r},'w').close()"])
    assert not marker.exists()


def test_cancel_registered_child_and_reject_late_registration():
    scope = RuntimeLifecycle()
    with scope.activate():
        child = spawn([sys.executable, "-c", "import time; print('ready',flush=True); time.sleep(60)"])
    try:
        assert child.stdout.readline().strip() == "ready"
        assert scope.cancel() == []
        assert child.wait(timeout=5) != 0
        assert scope.cancel() == []
        late = []
        with pytest.raises(RuntimeError, match="cancelled"):
            scope.register(lambda: late.append("stopped"))
        assert late == ["stopped"]
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_wedged_starts_and_controls_hold_bounded_slots(tmp_path):
    supervisor = make_supervisor(make_factory(tmp_path), _Clock(), start_timeout_s=.02)
    peers = [FakeConnector(wedge_start=True) for _ in range(4)]
    try:
        for index, peer in enumerate(peers):
            with pytest.raises(OktoNexusError, match="cancellation requested"):
                supervisor._bounded_start(peer, owning_agent_id="worker", kind="pi", binding_key=str(index))
        assert len(supervisor._quarantined_bindings) == 4
        with pytest.raises(OktoNexusError, match="capacity exhausted"):
            supervisor._bounded_start(FakeConnector(), owning_agent_id="worker", kind="pi")
        release = threading.Event()
        try:
            for _ in range(4):
                with pytest.raises(OktoNexusError, match="did not complete"):
                    supervisor._bounded_call(release.wait, timeout_s=.01, label="fixture")
            with pytest.raises(OktoNexusError, match="capacity exhausted"):
                supervisor._bounded_call(lambda: None, timeout_s=.01, label="fixture")
        finally:
            release.set()
    finally:
        for peer in peers:
            peer._never.set()
    assert wait_until(lambda: not supervisor._quarantined_bindings)
    assert all(peer.close_called for peer in peers)
    assert supervisor.list_live() == []


def test_real_codex_transport_handshake_timeout_kills_owned_fixture(tmp_path):
    # Production Codex transport, fixture executable intentionally never replies.
    marker = tmp_path / "pid"
    code = f"import os,time; open({str(marker)!r},'w').write(str(os.getpid())); time.sleep(60)"
    peer = CodexAppServerConnector(command=[sys.executable, "-c", code],
                                  env=fixture_environment(), handshake_timeout_s=30)
    supervisor = make_supervisor(make_factory(tmp_path), _Clock(), start_timeout_s=1)
    began = time.monotonic()
    with pytest.raises(OktoNexusError, match="cancellation requested"):
        supervisor._bounded_start(peer, owning_agent_id="worker", kind="codex", binding_key="fixture")
    assert marker.exists(), "test must reach actual spawn before timeout"
    assert time.monotonic() - began < 3
    assert wait_until(lambda: "fixture" not in supervisor._quarantined_bindings)
    assert peer._transport is None
    assert supervisor.list_live() == []


def test_rest_owner_start_timeout_has_no_running_session(runtime, tmp_path):
    deps, client, root, _, operator_key, _ = runtime
    with deps.connection_factory.unit_of_work(write=False) as uow:
        worker_before = dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='worker'").fetchone())
        agent_count = uow.connection.execute("SELECT count(*) FROM agents").fetchone()[0]
    marker = tmp_path / "production-spawn.pid"
    code = f"import os,time; open({str(marker)!r},'w').write(str(os.getpid())); time.sleep(60)"
    deps.harness_connector_factories["codex"] = lambda **_: CodexAppServerConnector(
        command=[sys.executable, "-c", code], env=fixture_environment(), handshake_timeout_s=30)
    supervisor = deps.harness_supervisor
    supervisor._start_timeout_s = 1
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator_key},
        json={"agent_id": "worker", "kind": "codex", "project_root": root,
              "idempotency_key": "fixture-timeout"})
    assert response.status_code >= 400
    assert marker.exists(), response.text
    assert wait_until(lambda: not supervisor._quarantined_bindings)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM harness_sessions").fetchone()[0] == 0
        assert uow.connection.execute("SELECT count(*) FROM runtime_open_requests").fetchone()[0] == 1
        assert dict(uow.connection.execute("SELECT * FROM agents WHERE agent_id='worker'").fetchone()) == worker_before
        assert uow.connection.execute("SELECT count(*) FROM agents").fetchone()[0] == agent_count
    # Repeating the same request must not launch the uncertain operation again.
    marker.unlink()
    retry = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator_key},
        json={"agent_id": "worker", "kind": "codex", "project_root": root,
              "idempotency_key": "fixture-timeout"})
    assert retry.status_code >= 400
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object contract")
@pytest.mark.parametrize("iteration", range(3))
def test_abrupt_owner_death_reaps_child_and_grandchild(tmp_path, iteration):
    # Hold process handles before killing the owner. Waiting on a handle proves
    # death of that process instance; a recycled numeric PID cannot satisfy it.
    child_script = tmp_path / "child.py"
    child_script.write_text("import subprocess,sys,os,time,json\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
        "print(json.dumps([os.getpid(),child.pid]),flush=True)\ntime.sleep(60)\n")
    owner_script = tmp_path / "owner.py"
    owner_script.write_text("import subprocess,sys,time\n"
        "from okto_nexus.adapters.outbound.harness.owned_process import spawn_owned_process\n"
        "p=spawn_owned_process([sys.executable,sys.argv[1]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)\n"
        "print(p.stdout.readline(),flush=True)\ntime.sleep(60)\n")
    environment = fixture_environment()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    owner = subprocess.Popen([sys.executable, str(owner_script), str(child_script)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handles = []
    try:
        pids = json.loads(owner.stdout.readline())
        for pid in pids:
            handle = kernel.OpenProcess(0x100000, False, pid)
            assert handle
            handles.append(handle)
            assert kernel.WaitForSingleObject(handle, 0) == 258  # alive
        owner.kill()
        owner.wait(timeout=5)
        for handle in handles:
            assert kernel.WaitForSingleObject(handle, 5000) == 0  # signalled
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)
        for handle in handles:
            kernel.CloseHandle(handle)
