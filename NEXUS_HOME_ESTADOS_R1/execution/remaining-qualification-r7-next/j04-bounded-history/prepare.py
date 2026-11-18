"""Write static pins only; no app import, dataset allocation, SQL or worker."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PERF = REPO / "NEXUS_HOME_ESTADOS_R1/execution/performance-hst"
COMPAT = HERE.parent / "compat-batch"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for name in ("worker.py", "run.py", "prepare.py"):
    ast.parse((HERE / name).read_text(encoding="utf-8"))
prior = json.loads((COMPAT / "PREPARED-S3-R9-v2.json").read_text(encoding="utf-8"))
original = PERF / "original-open-dataset.json"
dataset = Path(r"C:/Users/jpamb/AppData/Local/Temp/nexus-hst-performance-open-c7deab6559c14026bbedef93822237d9/dataset.json")
metadata = json.loads(original.read_text(encoding="utf-8"))
case = metadata["cases"][0]
ready = REPO / "NEXUS_HOME_ESTADOS_R1/execution/package-hst-r9/READY.json"
ready_data = json.loads(ready.read_text(encoding="utf-8"))
helpers = [HERE / name for name in ("worker.py", "run.py", "plan.md", "prepare.py")]
helpers += [original, dataset, PERF / "benchmark.py", PERF / "persistent-worker.py", PERF / "dataset.py",
    REPO / "NEXUS_UI_R1/execution/fixtures.py", Path(prior["command_helper"]), Path(prior["environment_helper"])]
manifest = {
    "status": "PREPARED_NOT_EXECUTED", "gate": "ROOT_APPROVED_J04_FUNCTIONAL", "scenario": "HST-T-J04 functional materialization clause only",
    "source_commit": ready_data["source_commit"], "ready": str(ready), "ready_sha256": sha(ready), "wheel_sha256": ready_data["wheel_sha256"],
    "source_pins": prior["source_pins"], "payload_files": prior["runtime_payloads"]["r9"]["files"],
    "helper_sha256": {str(path): sha(path) for path in helpers},
    "original_dataset": str(dataset), "original_dataset_sha256": sha(dataset), "original_metadata_sha256": sha(original),
    "seed_database_sha256": case["database_sha256"], "schema_sha256": case["schema_sha256"], "clock": metadata["clock"],
    "command_helper": prior["command_helper"], "environment_helper": prior["environment_helper"],
    "expected": {"original_connections": 100, "original_open_activities": 1000, "history_events": 100000, "additional_terminal_results": 25,
        "large_artifacts": 25, "large_history_payloads": 10, "GETs": 4, "result_pages": 2, "page_limit": 3, "board_preview_limit": 2},
    "bounds": {"worker_seconds": 180, "stdin": "closed PIPE", "new_processes_or_network_in_worker": "forbidden except qualified internal socketpair depth"},
    "static_checks": {"AST": "PASS", "Ruff_0_17_5": "PASS", "app_started": False, "clone_allocated": False},
    "limits": ["SQL synthetic facts, not canonical native execution or authority", "No p95/latency collection and no optimization", "Original OPEN seed remains immutable", "No human/browser/production qualification", "No O(page) or SQL scan bound claim from row materialization instrumentation"]}
assert len(manifest["source_pins"]) == 1829 and len(manifest["payload_files"]) == 1031
path = HERE / "PREPARED.json"
assert not path.exists()
path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"manifest_sha256": sha(path), "worker_sha256": sha(HERE / "worker.py"), "runner_sha256": sha(HERE / "run.py")}, indent=2))
