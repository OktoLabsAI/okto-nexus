"""Public final functional curation; no application, SQL or timing execution."""
import hashlib
import json
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:/Users/jpamb/AppData/Local/Temp/nexus-hst-j04-functional-4luo_glc")
OUT = HERE / "attempt3"
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
assert final["before"] == final["after"] and final["original_seed_unchanged"]
assert final["commands"][0]["exit_code"] == 0 and not final["commands"][0]["timed_out"]
pid = final["commands"][0]["pid"]
assert not psutil.pid_exists(pid), "If PID was reused, inspect birth; never signal"
mapping = result["canonical_artifact_paths"]
assert len(mapping) == 25 and {item["artifact_id"] for item in mapping} == {f"j04-synthetic-artifact-{index:03}" for index in range(25)}
assert all(Path(item["canonical_path"]).is_relative_to(ROOT) and Path(item["canonical_path"]).is_file() for item in mapping)
assert result["instrumentation"]["guarded_artifact_ids"] == 25
assert result["instrumentation"]["guarded_canonical_payload_paths"] == len({item["canonical_path"] for item in mapping})
assert not result["instrumentation"]["full_payload_materialized"]
assert not result["instrumentation"]["artifact_content_sql_reads"] and not result["instrumentation"]["artifact_file_reads"]
assert len(result["reads"]) == 4 and all(read["http_status"] == 200 for read in result["reads"])
assert result["productive_rows_unchanged"] and not result["payload_drift"]
save("worker-result.json", result)
save("partial-read-diagnostics.json", partial)
save("final-guards-and-cleanup.json", final)
save("canonical-artifact-path-mapping.json", {"count": len(mapping), "unique_paths": len({item["canonical_path"] for item in mapping}), "items": mapping,
    "guard_installed_before_four_GETs": True, "capture_scope": "Only artifact_id/storage_path metadata after bootstrap; no content read by capture"})
qualification = {
    "status": "PASS_FUNCTIONAL_J04_SCOPE", "source_commit": "f07163ab7fd618b2ff4247ba6cdb2547b5d4e038",
    "wheel_sha256": "e870ea400435d5b736093990af9b56544661e205ad657bbff83f830421a3e628",
    "ready_sha256": "028274a46776dbc677f096dc6e5493e102c683bd7e87eee1930c21f56111a631",
    "manifest_sha256": sha(HERE / "PREPARED-v3.json"), "gate_sha256": sha(HERE / "ROOT-GATE-v3.json"),
    "runner_sha256": sha(HERE / "run_v3.py"), "worker_sha256": sha(HERE / "worker_v3.py"), "runner_exit_code": 0,
    "volume": result["volume"], "reads": result["reads"], "instrumentation": result["instrumentation"],
    "assertions_executed": ["1000 original open activities and100000 history events remain;25 additional terminal results",
        "Synthetic foreign keys valid;131133-byte marked fields in result/event/artifact fixtures",
        "Exactly25 expected artifact IDs map to concrete canonical files inside the owned root before GET instrumentation",
        "Both canonical storage payload paths and original synthetic artifact directory protected by audit hook",
        "Overview nonempty; board cards present with column limit3/event preview2",
        "Results page1/page2 each3, disjoint IDs, exact total25, actual cursor and nonempty artifact metadata",
        "Result previews <=401 characters", "No full-field marker in materialized Python SQL rows or response bytes",
        "No artifacts.content SQL read; no protected artifact file open", "Productive-table hashes unchanged during GETs"],
    "module_origins": result["origins"], "guards_before": final["before"], "guards_after": final["after"],
    "original_seed_unchanged": True, "physical": {"worker_pid": pid, "absent_at_curation": True, "remaining": [], "forced": [], "timeout": False},
    "input_readers_released": True, "latencies_collected": False, "provider_invocations": 0,
    "layer": result["layer"], "raw_worker_output_sha256": final["commands"][0]["raw_sha256"],
    "antecedents": [{"path": "../attempt1/qualification.json", "sha256": sha(HERE / "attempt1/qualification.json"), "status": "422 runner precondition failure preserved"},
        {"path": "../attempt2/qualification.json", "sha256": sha(HERE / "attempt2/qualification.json"), "status": "Scoped pass with previous canonical-file-hook limitation preserved"}],
    "limits": ["Functional materialization clause only; not a new performance benchmark or target judgment",
        "SQL synthetic read facts with invalid/non-native receipt/event chains; no runtime/grant/authority qualification",
        "GET instrumentation excludes bootstrap initialization/migration work", "Complete metadata materialization16123rows does not prove O(page) cost or a global memory bound",
        "Guarded25 canonical payload files plus original directory, not a universal filesystem audit", "No provider/browser/human acceptance claim",
        "No raw transcript/payload/artifact file contents or private log copied"]}
save("qualification.json", qualification)
(OUT / "report.md").write_text("# J04 functional v3\n\nPASS in declared installed SQL-synthetic scope.1000 open activities and100000 history events remain;25 terminal results with131133-byte marked fields were added only to the copied dataset. After bootstrap the metadata-only capture mapped exactly25 artifact IDs to25 concrete canonical payload files inside the owned root. The audit hook protected those files and the original synthetic directory before the same four GETs.\n\nAll four returned200. Results pages contain3+3 distinct IDs from an exact total25, real cursors and artifact metadata. Board limits/previews and<=401-character result previews passed. Observed16123 materialized rows, maximum string17680 bytes, no full-field marker hits, no artifacts.content SQL reads and no protected file opens. Productive hashes, original seed, source1829/payload1031 guards remained unchanged.\n\nNormal worker exit0; timeoutfalse, force0, physical remaining0. No latency measurement. Bootstrap work is excluded, no O(page)/global memory claim, no native authority, provider or human qualification. Attempt1 failure and attempt2 limited file-hook coverage remain unchanged.\n", encoding="utf-8")
save("manifest.json", {path.name: sha(path) for path in OUT.iterdir()})
print(json.dumps({"qualification_sha256": sha(OUT / "qualification.json"), "manifest_sha256": sha(OUT / "manifest.json"), "input_readers_released": True}, indent=2))
