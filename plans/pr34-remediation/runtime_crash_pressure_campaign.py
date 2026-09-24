"""Bounded CPU contention and repeated real serve-owner death; fixtures only."""
import argparse
import ctypes
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]
import runtime_serve_shutdown_fixture as fixture  # noqa: E402

PIN = r"""
import ctypes,os
if os.name == 'nt':
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.GetCurrentProcess.restype=ctypes.c_void_p
    k.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
    k.SetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
    available,system=ctypes.c_size_t(),ctypes.c_size_t()
    assert k.GetProcessAffinityMask(k.GetCurrentProcess(),ctypes.byref(available),ctypes.byref(system))
    cpu_mask=available.value & -available.value
    assert k.SetProcessAffinityMask(k.GetCurrentProcess(),cpu_mask)
    affinity=cpu_mask.bit_length()-1
else:
    affinity=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{affinity})
"""

LOAD = PIN + r"""
import json,sys,time
from pathlib import Path
root=Path(sys.argv[1]); name=sys.argv[2]
began=time.monotonic(); deadline=began+300; last=0; iterations=0; value=1; retries=0
while time.monotonic()<deadline and not (root/'stop').exists():
    if not (root/'active').exists():
        time.sleep(.01)
    for _ in range(20000 if (root/'active').exists() else 0):
        value=(value*1664525+1013904223)&0xffffffff
    iterations+=20000 if (root/'active').exists() else 0
    now=time.monotonic()
    if now-last>.2:
        data={'affinity':affinity,'cpu_seconds':time.process_time(),'wall_seconds':now-began,'iterations':iterations,'publication_retries':retries}
        temporary=root/(name+'.tmp'); temporary.write_text(json.dumps(data))
        publish_deadline=min(deadline,time.monotonic()+2)
        while True:
            try:
                temporary.replace(root/(name+'.json'))
                break
            except PermissionError:
                retries+=1
                if time.monotonic()>=publish_deadline:
                    raise
                time.sleep(.01)
        last=now
"""


def resources(pid=None):
    gc.collect()
    pid = pid or os.getpid()
    if os.name == "nt":
        from ctypes import wintypes
        class Memory(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Memory), wintypes.DWORD]
        handle = kernel.OpenProcess(0x410, False, pid)
        assert handle
        try:
            memory, count = Memory(), wintypes.DWORD()
            memory.cb = ctypes.sizeof(memory)
            assert psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb)
            assert kernel.GetProcessHandleCount(handle, ctypes.byref(count))
            mask, system = ctypes.c_size_t(), ctypes.c_size_t()
            assert kernel.GetProcessAffinityMask(handle, ctypes.byref(mask), ctypes.byref(system))
            affinity = [i for i in range(64) if mask.value & (1 << i)]
            rss, handles = memory.WorkingSetSize, count.value
        finally:
            kernel.CloseHandle(handle)
    else:
        rss = int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        handles = len(list(Path(f"/proc/{pid}/fd").iterdir()))
        affinity = sorted(os.sched_getaffinity(pid))
    return {"rss_bytes": rss, "handles_or_fds": handles, "affinity": affinity,
        "python_threads": threading.active_count() if pid == os.getpid() else None}


class ExactOwner:
    """Hold the actual serve process, independently of a venv launcher wrapper."""
    def __init__(self, pid):
        if os.name == "nt":
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.kernel.OpenProcess.restype = wintypes.HANDLE
            self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = self.kernel.OpenProcess(0x100001, False, pid)
            assert self.handle and self.kernel.WaitForSingleObject(self.handle, 0) == 258
        else:
            from okto_nexus.adapters.outbound.harness.linux_process_guardian import pidfd_open
            self.handle = pidfd_open(pid)

    def kill(self):
        if os.name == "nt":
            assert self.kernel.TerminateProcess(self.handle, 91)
            assert self.kernel.WaitForSingleObject(self.handle, 5000) == 0
        else:
            import select
            import signal
            from okto_nexus.adapters.outbound.harness.linux_process_guardian import pidfd_send_signal
            pidfd_send_signal(self.handle, signal.SIGKILL)
            assert select.select([self.handle], [], [], 5)[0]

    def close(self):
        if os.name == "nt":
            self.kernel.CloseHandle(self.handle)
        else:
            os.close(self.handle)


def load_snapshot(root):
    return [json.loads((root / f"load-{index}.json").read_text()) for index in range(2)]


def campaign(iterations, output):
    assert 3 <= iterations <= 12
    result = {"status": "RUNNING", "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "campaign_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(Path(fixture.__file__).read_bytes()).hexdigest(),
        "platform": sys.platform, "load_workers": 2, "warmup_cycles": 2, "measured_cycles": iterations,
        "samples": [], "limitations": ["Synthetic Pi protocol peer; no provider/model", "Single allowed CPU pinned only inside owned fixture processes",
            "Load starts after protocol readiness; not a startup-under-pressure claim",
            "Bounded contention; not host-wide exhaustion or comparative latency benchmark", "RSS and descriptor limits apply to the campaign process; each serve/peer tree has exact death witnesses"]}
    with tempfile.TemporaryDirectory(prefix="okto-crash-pressure-") as directory:
        root = Path(directory)
        script = root / "load.py"
        script.write_text(LOAD, encoding="utf-8")
        env = {k:v for k,v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        env.update(HOME=str(root), USERPROFILE=str(root), PYTHONIOENCODING="utf-8")
        workers = []
        original = fixture.LAUNCHER
        # All owned serve instances and load workers select the same allowed CPU.
        fixture.LAUNCHER = PIN + "\nimport sys,json\nfrom pathlib import Path\n" + (
            "Path(sys.argv[2]).with_name('actual-owner.json').write_text(json.dumps({'pid':os.getpid(),'affinity':affinity}))\n") + original
        try:
            for index in range(2):
                workers.append(subprocess.Popen([sys.executable, str(script), str(root), f"load-{index}"], env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
            deadline = time.monotonic() + 10
            while not all((root / f"load-{i}.json").exists() for i in range(2)):
                assert time.monotonic() < deadline and all(p.poll() is None for p in workers)
                time.sleep(.02)
            for index in range(iterations + 2):
                assert all(p.poll() is None for p in workers)
                cycle_root = root / f"cycle-{index}"
                cycle_root.mkdir()
                serve = fixture.ServeFixture(cycle_root)
                actual_owner = json.loads((cycle_root / "actual-owner.json").read_text())
                owner_witness = ExactOwner(actual_owner["pid"])
                try:
                    serve.open()
                    (root / "active").touch()
                    time.sleep(.3)
                    before = load_snapshot(root)
                    time.sleep(1.2)
                    owned_resources = resources(actual_owner["pid"])
                    after = load_snapshot(root)
                    elapsed = min(b["wall_seconds"] - a["wall_seconds"] for a,b in zip(before,after))
                    cpu_seconds = sum(b["cpu_seconds"] - a["cpu_seconds"] for a,b in zip(before,after))
                    assert elapsed > 0 and cpu_seconds / elapsed > .25, (before,after)
                    assert len({row["affinity"] for row in after}) == 1
                    assert owned_resources["affinity"] == [after[0]["affinity"]], (owned_resources["affinity"],after)
                    assert all(b["iterations"] > a["iterations"] for a,b in zip(before,after))
                    started = time.monotonic()
                    owner_witness.kill()
                    serve.process.wait(timeout=20)
                    for witness in serve.witnesses:
                        witness.assert_stopped()
                    reap_seconds = time.monotonic() - started
                    assert serve.process.returncode != 0
                    witnessed = len(serve.witnesses)
                finally:
                    (root / "active").unlink(missing_ok=True)
                    serve.close()
                    owner_witness.close()
                sample = {"cycle": index, "load_cpu_seconds": cpu_seconds, "load_wall_seconds": elapsed,
                    "load_cpu_fraction": cpu_seconds / elapsed, "load_affinity": after[0]["affinity"],
                    "owner_affinity_verified": actual_owner["affinity"] == after[0]["affinity"],
                    "load_iterations_delta": sum(b["iterations"]-a["iterations"] for a,b in zip(before,after)),
                    "exact_tree_reaps": witnessed, "reap_seconds": reap_seconds, "owner_before_kill": owned_resources,
                    "campaign_after_reap": resources()}
                if index == 1:
                    result["baseline"] = sample["campaign_after_reap"]
                if index >= 2:
                    result["samples"].append(sample)
                print(json.dumps({"cycle":index,"exact_tree_reaps":witnessed,"reap_seconds":reap_seconds}),flush=True)
            baseline = result["baseline"]
            result["limits"] = {"rss_bytes": baseline["rss_bytes"] + 16*1024*1024,
                "handles_or_fds": baseline["handles_or_fds"]+8, "python_threads": baseline["python_threads"]+2}
            assert all(s["campaign_after_reap"][k] <= v for s in result["samples"] for k,v in result["limits"].items()), result
            result["status"] = "PASS"
        except BaseException as exc:
            result["status"] = "FAIL"
            result["failure"] = {"type": type(exc).__name__, "message": str(exc)[:1500]}
            raise
        finally:
            fixture.LAUNCHER = original
            (root / "stop").touch()
            for process in workers:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            result["load_workers_reaped"] = all(p.poll() is not None for p in workers)
            output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cycles", type=int, default=6)
    args = parser.parse_args()
    result = campaign(args.cycles, args.output)
    args.output.write_text(json.dumps(result, indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"measured_cycles":result["measured_cycles"]}),flush=True)


if __name__ == "__main__":
    main()
