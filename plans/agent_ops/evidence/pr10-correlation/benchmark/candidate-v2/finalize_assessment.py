"""Close public V4 benchmark evidence without reading private fixture files."""
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parent / "pr10b-installed-benchmark-v3-fr9dtadn"
WHEEL = "fc9bb8f075ac0167eee9c21d96592b12d46c218df77a0f2114f44b1fc20b1355"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def metadata(path):
    content = path.read_bytes()
    return {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def summarize(report):
    return [
        {
            "sessions": layout["sessions"],
            "instances": stage["instances"],
            "reads": {
                name: {
                    "samples_total": len(reading["samples"]),
                    "samples_successful": sum(s["ok"] for s in reading["samples"]),
                    "median_success_ms": statistics.median(
                        s["elapsed_ms"] for s in reading["samples"] if s["ok"]
                    ) if any(s["ok"] for s in reading["samples"]) else None,
                    "max_success_ms": max(
                        (s["elapsed_ms"] for s in reading["samples"] if s["ok"]),
                        default=None,
                    ),
                    "budget_refusals": sum(
                        s.get("error", {}).get("code") == "ATTENTION_QUERY_BUDGET"
                        for s in reading["samples"]
                    ),
                    "select_or_cte_counts": sorted({s["select_or_cte"] for s in reading["samples"]}),
                    "sample_ms_in_recorded_order": [s["elapsed_ms"] for s in reading["samples"]],
                }
                for name, reading in stage["reads"].items()
            },
        }
        for layout in report["layouts"] for stage in layout["stages"]
    ]


report = read(ROOT / "benchmark-installed.json")
prior = read(PRIOR / "benchmark-installed.json")
assert report["status"] == "COMPLETED_MEASUREMENTS"
assert report["package"]["wheel_sha256"] == WHEEL
assert [l["sessions"] for l in report["layouts"]] == [1, 64]
assert all([s["instances"] for s in l["stages"]] == [64, 512, 4096] for l in report["layouts"])
assert report["quotas"] == prior["quotas"]
assert report["deadline_seconds"] == prior["deadline_seconds"] == 5
assert (ROOT / "benchmark_installed.py").read_bytes() == (PRIOR / "benchmark_installed.py").read_bytes()
samples = [s for l in report["layouts"] for stage in l["stages"] for r in stage["reads"].values() for s in r["samples"]]
assert len(samples) == 90
assert all(len(r["samples"]) == 3 for l in report["layouts"] for stage in l["stages"] for r in stage["reads"].values())
assert all(stage["canonical_tables_unchanged"] and stage["canonical_table_count"] == 145 for l in report["layouts"] for stage in l["stages"])
assert all(l["package_after"]["product_imports_only_installed"] and l["package_after"]["verified_files"] == 681 and l["package_after"]["wheel_sha256"] == WHEEL and l["package_after"]["core_version"] == "0.0.14" for l in report["layouts"])
write_classes = sorted({name for s in samples for name in s["statement_classes"] if name in {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP", "VACUUM", "REINDEX"}})
assert not write_classes
success = sum(s["ok"] for s in samples)
refusals = sum(s.get("error", {}).get("code") == "ATTENTION_QUERY_BUDGET" for s in samples)
assessment = {
    "status": "MEASUREMENTS_COMPLETED_ALL_SAMPLES_PASSED" if success == 90 else "MEASUREMENTS_COMPLETED_WITH_REFUSALS_OR_FAILURES",
    "wheel_sha256": WHEEL,
    "samples_total": len(samples),
    "samples_successful": success,
    "budget_refusals": refusals,
    "other_failures": len(samples) - success - refusals,
    "sample_retries": 0,
    "measurement_driver_exact_bytes_equal_v3": True,
    "approved_layouts": [1, 64],
    "scales": [64, 512, 4096],
    "samples_per_read": 3,
    "states": {"blocked": 0.5, "working": 0.5},
    "all_correlated": True,
    "receipts_per_session": 12,
    "deadline_seconds": 5,
    "first_cold_or_less_warm_samples_retained": True,
    "not_qualified": ["4096 unique native sessions", "general latency SLO", "real OS birth proof"],
    "canonical_row_fingerprints_unchanged": True,
    "canonical_tables_per_stage": 145,
    "fingerprint_exclusions": ["observation_*", "attention_*", "events"],
    "measured_trace_write_classes": write_classes,
    "product_imports_only_installed_before_and_after": True,
    "raw_report_sha256": metadata(ROOT / "benchmark-installed.json")["sha256"],
    "factories_closed": True,
    "closure_evidence": "Each campaign returns through connection_factory.close() in finally; both returned and the process exited 0.",
    "process_exit_code": 0,
    "process_session": 82635,
    "started_at": report["started_at"],
    "finished_at": report["finished_at"],
    "summary": summarize(report),
    "comparison": {
        "prior_campaign": "V3 against candidate-v1",
        "prior_raw_report_sha256": metadata(PRIOR / "benchmark-installed.json")["sha256"],
        "prior_samples_total": 90,
        "prior_samples_successful": 86,
        "prior_budget_refusals": 4,
        "same_driver_workload_quotas_and_deadline": True,
        "prior_64_sessions_4096_instances": next(s for s in summarize(prior) if s["sessions"] == 64 and s["instances"] == 4096),
        "limit": "Three local samples include trace overhead and retain the first colder sample; no general latency SLO. Earlier OBS11 had completions and is a different workload.",
    },
}
assert not (ROOT / "assessment.json").exists()
(ROOT / "assessment.json").write_text(json.dumps(assessment, indent=2) + "\n", encoding="utf-8")
manifest = read(ROOT / "manifest-before-campaign.json")
manifest.update(
    status=assessment["status"],
    samples_total=len(samples),
    samples_successful=success,
    budget_refusals=refusals,
    sample_retries=0,
    canonical_row_fingerprints_unchanged=True,
    factories_closed=True,
    process_exit_code=0,
)
public_files = [
    "benchmark_installed.py", "preflight.py", "README.md", "parent-v3-manifest.json",
    "preflight.json", "manifest-before-campaign.json", "benchmark-installed.json",
    "assessment.json", "finalize_assessment.py",
]
manifest["files"] = {name: metadata(ROOT / name) for name in public_files}
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"manifest": metadata(ROOT / "manifest.json"), "assessment": metadata(ROOT / "assessment.json"), "raw_report": metadata(ROOT / "benchmark-installed.json"), "samples": [len(samples), success, refusals]}, indent=2))
