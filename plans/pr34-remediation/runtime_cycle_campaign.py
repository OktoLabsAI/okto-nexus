"""Repeat production HTTP runtime cycles with owned Python protocol peers only."""
import ctypes
import gc
import json
import hashlib
import logging
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))
from test_pr34_remediation import runtime, tool  # noqa: E402
from test_runtime_commands import wait_close_result, wait_operation  # noqa: E402
from test_runtime_effective_capabilities import open_codex  # noqa: E402


def resources():
    gc.collect()
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        count = ctypes.c_ulong()
        if not kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count)):
            raise ctypes.WinError(ctypes.get_last_error())
        handles = count.value
    else:
        handles = len(list(Path("/proc/self/fd").iterdir()))
    return {"threads": threading.active_count(), "handles_or_fds": handles,
        "python_bytes": tracemalloc.get_traced_memory()[0]}


def cycle(current):
    deps, client, _, _, operator, _ = current
    started = time.monotonic()
    session = open_codex(current)
    native = deps.harness_supervisor._live[session["session_id"]].connector.native
    process = native._transport._proc
    for text in ("isolated cycle one", "isolated cycle two"):
        admitted = tool(client, operator, "harness_send", {"session_id": session["session_id"], "payload": {"text": text}})
        assert admitted["ok"], admitted
        result = wait_operation(current, admitted["data"]["operation_id"], lambda row: row["result_durable"])
        assert text in result["result"]["output_text"]
    closed = tool(client, operator, "harness_close", {"session_id": session["session_id"]})
    assert wait_close_result(client, operator, closed)["lifecycle_state"] == "stopped"
    assert process.wait(timeout=5) is not None
    assert deps.harness_supervisor.get(session["session_id"]) is None
    return time.monotonic() - started


def main():
    logging.disable(logging.INFO)
    from okto_nexus.application import runtime_dispatcher
    assert Path(runtime_dispatcher.__file__).resolve().is_relative_to(REPO)
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    diff = subprocess.check_output(["git", "diff", "--binary", "HEAD", "--", "src", "tests"], cwd=REPO)
    tracemalloc.start()
    with tempfile.TemporaryDirectory(prefix="okto-owned-cycle-") as directory:
        fixture = runtime.__wrapped__(Path(directory), SimpleNamespace(param=True))
        current = next(fixture)
        samples, durations = [], []
        try:
            for _ in range(2):
                cycle(current)
            baseline = resources()
            for _ in range(12):
                durations.append(cycle(current))
                samples.append(resources())
            limits = {"threads": baseline["threads"] + 4,
                "handles_or_fds": baseline["handles_or_fds"] + 16,
                "python_bytes": baseline["python_bytes"] + 4 * 1024 * 1024}
            methods = [json.loads(line).get("request_method") for line in
                (Path(current[2]) / "capability-wire.jsonl").read_text().splitlines()]
            methods = sorted({method for method in methods if method})
            within_limits = all(sample[key] <= limit for sample in samples for key, limit in limits.items())
            result = {"source_sha": source_sha, "source_dirty_diff_sha256": hashlib.sha256(diff).hexdigest(),
                "campaign_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "status": "PASS" if within_limits else "FAIL", "warmup_cycles": 2,
                "measured_cycles": 12, "turns_per_cycle": 2, "baseline": baseline,
                "limits": limits, "samples": samples, "fixture_request_methods": methods,
                "median_cycle_seconds": statistics.median(durations),
                "max_cycle_seconds": max(durations), "process_stop_observed_each_cycle": True,
                "limitations": ["Python protocol peer, no provider/native model",
                    "Python allocations, not RSS", "steady cycles, not crash-pressure or comparative performance",
                    "host may concurrently execute other test suites"]}
            Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2))
        finally:
            try:
                next(fixture)
            except StopIteration:
                pass


if __name__ == "__main__":
    main()
