"""Preserve failed runner precondition; no new app, SQL, or measurement."""
import hashlib
import json
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:/Users/jpamb/AppData/Local/Temp/nexus-hst-j04-functional-1p8prkpe")
OUT = HERE / "attempt1"
assert not OUT.exists()
OUT.mkdir()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


final = json.loads((ROOT / "final.json").read_text())
result = json.loads((ROOT / "result.json").read_text())
assert final["failure"] and final["commands"][0]["exit_code"] == 1
assert final["before"] == final["after"] and not final["remaining"] and not final["forced"]
assert not final["commands"][0]["timed_out"]
pid = final["commands"][0]["pid"]
assert not psutil.pid_exists(pid), "If reused, inspect birth before any conclusion; never signal"
save("final-guards-and-cleanup.json", final)
save("incomplete-worker.json", result)
raw = ROOT / "command-functional-history.private.txt"
trace = raw.read_text(encoding="utf-8").replace(str(HERE.parents[3]), "<REPO>").replace(str(ROOT), "<OWN_TEMP>")
(OUT / "failure-trace-redacted.txt").write_text(trace, encoding="utf-8")
qualification = {
    "status": "INCOMPLETE_RUNNER_PRECONDITION", "scenario_J04": "NOT_RUN_COMPLETE_CRITERIA",
    "source_commit": "f07163ab7fd618b2ff4247ba6cdb2547b5d4e038",
    "wheel_sha256": "e870ea400435d5b736093990af9b56544661e205ad657bbff83f830421a3e628",
    "manifest_sha256": sha(HERE / "PREPARED.json"), "gate_sha256": sha(HERE / "ROOT-GATE.json"),
    "runner_sha256": sha(HERE / "run.py"), "worker_sha256": sha(HERE / "worker.py"),
    "attempts": 1, "rerun": False, "runner_exit_code": 1,
    "observed_HTTP": [{"path": "/api/v1/home/overview", "status": 200},
        {"path": "/api/v1/home/harness-board", "status": 200},
        {"path": "/api/v1/home/results", "status": 422, "invalid_parameter": "quick=all"}],
    "fourth_GET": "NOT_RUN",
    "root_cause": "Runner sends unsupported quick parameter to legacy Home results route. http/home.py only allows workspace_id,agent_id,state,cursor,limit. Correct canonical rejection; not a product defect.",
    "remaining_assertions": {"full_payload_materialization": "NOT_QUALIFIED: partial in-memory instrumentation was not exported after assertion",
        "actual_results_pagination": "NOT_RUN", "productive_hashes_after_GETs": "NOT_RUN"},
    "volume": result["volume"], "module_origins": result["origins"], "payload_drift": result["payload_drift"],
    "source_and_payload_guards": final["after"], "original_seed_unchanged": final["original_seed_unchanged"],
    "physical": {"worker_pid": pid, "absent_at_curation": True, "remaining": [], "force": [], "timeout": False},
    "raw_trace_sha256": sha(raw), "raw_final_sha256": sha(ROOT / "final.json"),
    "latencies_collected": False, "provider_invocations": 0, "input_readers_released": True,
    "limits": ["SQL synthetic facts only, no canonical native/authority proof", "No new app/browser/test/SQL during curation", "No universal database read-only or materialization PASS", "Original failed scripts/assertions remain unchanged", "No timing or acceptance inference"]}
save("qualification.json", qualification)
(OUT / "report.md").write_text("# J04 attempt1 — incomplete, no retry\n\nThe first two functional GETs returned200. The third returned422 because the prepared worker supplied quick=all to the legacy results endpoint, which deliberately rejects unknown query parameters. The fourth GET and final pagination/materialization/productive-after assertions did not run. This is a runner-precondition failure, not a product defect.\n\nThe source1829/payload1031 guards match, original seed is unchanged, installed origins match, worker exited1 normally with no timeout/force/remaining. Only a synthetic owned clone was altered. No latency was collected. Any corrected runner requires a new immutable counterpart and Root gate.\n", encoding="utf-8")
save("manifest.json", {path.name: sha(path) for path in OUT.iterdir()})
print(json.dumps({"qualification_sha256": sha(OUT / "qualification.json"), "manifest_sha256": sha(OUT / "manifest.json")}, indent=2))
