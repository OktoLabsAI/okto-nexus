"""Public curation and RO path-scope check; no new app or functional GET."""
import hashlib
import json
from pathlib import Path
import sqlite3

import psutil

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:/Users/jpamb/AppData/Local/Temp/nexus-hst-j04-functional-t7lh0xy9")
OUT = HERE / "attempt2"
assert not OUT.exists()
OUT.mkdir()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


result = json.loads((ROOT / "result.json").read_text())
final = json.loads((ROOT / "final.json").read_text())
partial = json.loads((ROOT / "partial-read-diagnostics.json").read_text())
assert result["status"] == "PASS_FUNCTIONAL_HISTORY_SCOPE"
assert not final["failure"] and not final["remaining"] and not final["forced"]
assert final["before"] == final["after"]
assert final["commands"][0]["exit_code"] == 0 and not final["commands"][0]["timed_out"]
pid = final["commands"][0]["pid"]
assert not psutil.pid_exists(pid)
db = ROOT / "home/nexus.db"
before = sha(db)
with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as connection:
    paths = [{"artifact_id": row[0], "path": row[1], "content_characters": row[2],
        "original_file_hook_covers_current_path": bool(row[1]) and Path(row[1]).resolve().is_relative_to(ROOT / "synthetic-artifacts")}
        for row in connection.execute("SELECT artifact_id,path,length(content) FROM artifacts WHERE artifact_id LIKE 'j04-synthetic-artifact-%' ORDER BY artifact_id")]
assert sha(db) == before
save("postcut-readonly-artifact-path-scope.json", {"rows": paths, "count": len(paths), "db_hash_unchanged": True,
    "database_sha256": before, "purpose": "Posterior metadata-only check of audit-hook coverage; not a new functional execution or a retroactive assertion"})
for name, data in (("worker-result.json", result), ("final-guards-and-cleanup.json", final), ("partial-read-diagnostics.json", partial)):
    save(name, data)
fully_covered = len(paths) == 25 and all(row["original_file_hook_covers_current_path"] for row in paths)
qualification = {
    "status": "PASS_SCOPED_EXECUTED_ASSERTIONS", "J04_complete_judgment": "ROOT_REVIEW_REQUIRED_FOR_FILE_HOOK_SCOPE",
    "source_commit": "f07163ab7fd618b2ff4247ba6cdb2547b5d4e038",
    "wheel_sha256": "e870ea400435d5b736093990af9b56544661e205ad657bbff83f830421a3e628",
    "ready_sha256": "028274a46776dbc677f096dc6e5493e102c683bd7e87eee1930c21f56111a631",
    "manifest_sha256": sha(HERE / "PREPARED-v2.json"), "gate_sha256": sha(HERE / "ROOT-GATE-v2.json"),
    "runner_sha256": sha(HERE / "run_v2.py"), "worker_sha256": sha(HERE / "worker_v2.py"),
    "runner_exit_code": 0, "four_GETs": result["reads"], "volume": result["volume"], "instrumentation": result["instrumentation"],
    "executed_checks": ["1000 original OPEN activities and100000 synthetic events remain", "25 additional results with131133-byte marked fields and25 artifact files",
        "Foreign-key validation", "Overview and board nonempty", "Board limit3 and event preview2", "Two real results pages3+3 with exact total25 and disjoint IDs",
        "Nonempty artifact metadata", "Result preview<=401 characters", "No full-field marker in Python SQL rows or HTTP bytes",
        "No artifacts.content SQL reads", "No opens detected under original synthetic-artifacts directory", "Productive-table hashes unchanged during GETs"],
    "artifact_file_hook_all_current_paths_covered": fully_covered,
    "scope_notes": ["Instrumentation covers four GETs, not preceding bootstrap initialization or migration work",
        "The file audit hook covers only root/synthetic-artifacts; postcut current paths are listed separately. No universal filesystem no-read assertion.",
        "16123 metadata rows materialized across four GETs does not imply O(page) cost or memory bound", "SQL scans/JSON extraction are distinct from Python full-payload materialization"],
    "payload_drift": result["payload_drift"], "guards_before": final["before"], "guards_after": final["after"],
    "original_seed_unchanged": final["original_seed_unchanged"], "physical": {"worker_pid": pid, "absent_at_curation": True, "remaining": [], "forced": [], "timeout": False},
    "latencies_collected": False, "provider_invocations": 0, "input_readers_released": True,
    "layer": result["layer"], "raw_output_sha256": final["commands"][0]["raw_sha256"],
    "antecedent": {"path": "../attempt1/qualification.json", "sha256": sha(HERE / "attempt1/qualification.json"), "failure_preserved": True},
    "limits": ["SQL synthetic history/receipts; no native execution/authority proof", "No performance target, provider, browser or human acceptance inference",
        "Only allowlisted synthetic metadata/hashes copied; no transcript/payload/artifact content or private log copied"]}
save("qualification.json", qualification)
(OUT / "report.md").write_text("# J04 functional v2 — executed assertions pass\n\nFour GETs returned200. The results pages contain3+3 disjoint items from an exact total25, with actual artifact metadata. The original1000 OPEN activities/100000 events remain, plus25 terminal synthetic results. Large fields are131133 bytes. Across the GETs the observer saw16123 rows, maximum string17680 bytes, zero full-payload marker hits, zero artifacts.content SQL reads and zero file opens under the explicitly guarded synthetic artifact directory. Productive hashes and source/payload/seed guards remained unchanged.\n\nThe worker exited0, timeoutfalse, force0 and physical remaining0. No latency was collected. Bootstrap is outside GET instrumentation. File-hook scope is the original synthetic-artifacts directory; posterior RO metadata lists whether current artifact paths remain there. Do not turn that scoped observation into a universal filesystem claim. Root decides complete J04 judgment. The original422 attempt stays preserved.\n", encoding="utf-8")
save("manifest.json", {path.name: sha(path) for path in OUT.iterdir()})
print(json.dumps({"qualification_sha256": sha(OUT / "qualification.json"), "manifest_sha256": sha(OUT / "manifest.json"),
    "artifact_file_hook_all_current_paths_covered": fully_covered, "path_examples": paths[:2]}, indent=2))
