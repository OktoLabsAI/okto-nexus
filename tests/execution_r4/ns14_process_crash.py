"""Windows installed-Core containment acceptance with an owned laboratory tree."""
import asyncio
import ctypes
from ctypes import wintypes
from dataclasses import asdict, replace
import json
import os
import platform
import queue
import subprocess
import sys
import threading
import time

from nexus_connector_core import OperationKey, ProcessBirthEvidence, SessionKey
from nexus_connector_core.journal import SQLiteJournal
from nexus_connector_core.native.process import observe_recorded_process_birth

KEY = OperationKey("ns14-server", "ns14-executor", "ns14-open")
SESSION = SessionKey(KEY.server_id, KEY.executor_id, "ns14-session")
INTENT = "sha256:" + "c" * 64

OWNER = r"""
import asyncio,json,os,sys,time
from dataclasses import asdict
import nexus_connector_core
from nexus_connector_core import OperationKey
from nexus_connector_core.journal import SQLiteJournal
from nexus_connector_core.native.process import spawn_owned_process,snapshot_owned_process_birth
async def run():
    journal=SQLiteJournal(sys.argv[1])
    key=OperationKey("ns14-server","ns14-executor","ns14-open")
    await journal.admit(key,"sha256:"+"c"*64,"ns14-session",effect_imminent=True,
        claim_session=True,connection_generation=3,session_owner_generation=1)
    code="import subprocess,sys,os,json,time; child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']); print(json.dumps([os.getpid(),child.pid]),flush=True); time.sleep(120)"
    process=spawn_owned_process([sys.executable,"-I","-c",code],cwd=os.getcwd(),env=dict(os.environ),text=True)
    tree=json.loads(process.stdout.readline())
    birth=snapshot_owned_process_birth(process)
    if sys.argv[2]=="recorded":
        await journal.record_process_birth(key,"ns14-session",birth)
    print(json.dumps(dict(tree=list(set([birth.pid]+tree)),birth=asdict(birth),
        core_file=nexus_connector_core.__file__)),flush=True)
    time.sleep(120)
asyncio.run(run())
"""


def run_crash(root, stage, record_property):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    path = root / "owner.db"
    # This independent child is a negative control, owned by this test only.
    control = subprocess.Popen([sys.executable, "-I", "-c", "import time;time.sleep(120)"],
                               creationflags=subprocess.CREATE_NO_WINDOW)
    owner = subprocess.Popen([sys.executable, "-I", "-c", OWNER, str(path), stage],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    handles = []
    try:
        lines = queue.Queue(maxsize=1)
        threading.Thread(target=lambda: lines.put(owner.stdout.readline()), daemon=True).start()
        line = lines.get(timeout=20)
        assert line, "The laboratory owner exited before reporting its tree."
        report = json.loads(line)
        assert "site-packages" in report["core_file"]
        birth = ProcessBirthEvidence(**report["birth"])
        assert birth.containment == "windows_job"
        assert observe_recorded_process_birth(birth) == "MATCHING_LIVE"
        assert observe_recorded_process_birth(replace(birth, birth_token=birth.birth_token+"-stale")) == "DIFFERENT_BIRTH"
        assert observe_recorded_process_birth(ProcessBirthEvidence(
            "linux", control.pid, "foreign", "linux_guardian")) == "UNKNOWN"
        for pid in report["tree"]:
            handle = kernel.OpenProcess(0x00100001, False, pid)
            assert handle, "The reported laboratory tree member must be observable."
            handles.append(handle)
            assert kernel.WaitForSingleObject(handle, 0) == 258
        started = time.monotonic()
        owner.kill()
        owner.wait(timeout=10)
        for handle in handles:
            assert kernel.WaitForSingleObject(handle, 10_000) == 0
        elapsed = time.monotonic() - started
        assert control.poll() is None
        assert observe_recorded_process_birth(birth) in {"NOT_RUNNING", "NOT_OBSERVED"}

        async def inspect():
            journal = SQLiteJournal(path)
            try:
                receipt = await journal.get_receipt(KEY)
                assert receipt.stage == "SUBMISSION_STARTED" and receipt.possible_effect
                claims = (await journal.claimed_sessions(KEY.server_id, KEY.executor_id)).claims
                assert len(claims) == 1
                assert claims[0].opening_connection_generation == 3
                assert claims[0].opening_owner_generation == 1
                saved = await journal.get_process_birth(SESSION)
                if stage == "recorded":
                    assert saved.evidence == birth
                else:
                    assert saved is None
                replay, fresh = await journal.admit(KEY, INTENT, SESSION.session_id,
                    claim_session=True, connection_generation=3, session_owner_generation=1)
                assert not fresh and replay == receipt
            finally:
                journal.close()
        asyncio.run(inspect())
        record_property("ns14_process_crash", json.dumps(dict(
            platform=platform.platform(), stage=stage, containment="windows_job",
            tree_members=len(handles), stop_seconds=elapsed, unrelated_control_alive=True,
            durable_receipt="SUBMISSION_STARTED", possible_effect=True,
            missing_or_foreign_evidence="No ownership inferred; foreign platform remains UNKNOWN",
            topology="Installed Core; laboratory owner and child tree; no native provider")))
    finally:
        for process in (owner, control):
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        for handle in handles:
            if kernel.WaitForSingleObject(handle, 0) != 0:
                kernel.TerminateProcess(handle, 1)
                kernel.WaitForSingleObject(handle, 5000)
            kernel.CloseHandle(handle)
        for pipe in (owner.stdout, owner.stderr):
            pipe.close()
