"""Capture repository facts and map proposed tests to real collected node IDs.

This is an inventory, not a coverage or product acceptance oracle. Pass three
JSON reports from collect_tests.py, each collected in its repository root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root).decode("utf-8").strip()


def source_facts(root: Path) -> dict:
    # NUL records preserve filenames containing spaces. No reset/clean/staging.
    records = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=root
    ).decode("utf-8").split("\0")
    changes = []
    entries = iter(records)
    for record in entries:
        if not record:
            continue
        changes.append(record)
        # Under -z a rename/copy has a separate original-path field. It is
        # part of the status fingerprint, not another changed-file record.
        if "R" in record[:2] or "C" in record[:2]:
            next(entries)
    protected = {}
    for record in changes:
        path = root / record[3:]
        if path.is_file():
            protected[record[3:]] = digest(path)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    artifacts = {p.relative_to(root).as_posix(): digest(p)
                 for folder in (root / "artifacts", root / "dist",
                                root / "vendor/wheels", root / "vendor/ci")
                 for pattern in ("*.whl", "*.tar.gz")
                 for p in sorted(folder.glob(pattern)) if p.is_file()}
    wheels = {name: sha for name, sha in artifacts.items()
              if Path(name).name.startswith("nexus_connector_core-")
              and name.endswith(".whl")}
    return {
        "branch": git(root, "branch", "--show-current"),
        "head": git(root, "rev-parse", "HEAD"),
        "version": project["project"]["version"],
        "pyproject_sha256": digest(root / "pyproject.toml"),
        "lockfiles": {p.name: digest(p) for p in (root / "uv.lock", root / "package-lock.json") if p.exists()},
        "dirty_counts": dict(Counter(record[:2] for record in changes)),
        "dirty_status_sha256": hashlib.sha256("\0".join(records).encode()).hexdigest(),
        "preexisting_file_hashes": protected, "core_wheels": wheels,
        "distribution_artifacts": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("nexus", "connector", "core"):
        parser.add_argument(f"--{name}-collection", type=Path, required=True)
    parser.add_argument("--connector-root", type=Path, default=ROOT.parent / "okto-nexus-connector")
    parser.add_argument("--core-root", type=Path, default=ROOT.parent / "okto-nexus-connector-core")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collections = {name: json.loads(getattr(args, f"{name}_collection").read_text(encoding="utf-8"))
                   for name in ("nexus", "connector", "core")}
    backlog = json.loads((ROOT / "plans/BACKLOG_R4.json").read_text(encoding="utf-8"))
    matrix = json.loads((ROOT / "plans/MATRIZ_TESTES_R4.json").read_text(encoding="utf-8"))
    tasks = {}
    named_candidates = {
        "NS01.04": ["tests/execution_r4/test_ns01.py::test_v1_auth_is_bearer_only_and_direct"],
        "NS04.04": ["tests/execution_r4/test_ns04.py::test_remote_inventory_http_requires_executor_ticket"],
    }
    for task in backlog["tasks"]:
        proposed = task["test_command_proposed"].split("pytest ")[1].split(" ")[0]
        function = proposed.split("::")[-1]
        nodes = [node for node in collections["nexus"]["nodes"]
                 if (node == proposed or node.startswith(proposed + "[") or
                     (node.startswith("tests/execution_r4/") and
                      node.split("::")[-1].startswith(function + "_")) or
                     node in named_candidates.get(task["id"], []))]
        tasks[task["id"]] = {
            "proposed_nodeid": proposed, "collected_nodeids": nodes,
            "effective_test_command": "python -m pytest " + " ".join(nodes) + " -q" if nodes else None,
            "test_availability": "COLLECTED" if nodes else "MISSING",
            "implementation": "PARTIAL_REQUIRES_ACCEPTANCE" if nodes else "UNVERIFIED",
            "acceptance": "NOT_RUN", "required_scenarios": task["test_ids"],
        }
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "status": "INVENTORY_ONLY_NOT_PRODUCT_ACCEPTANCE",
        "repositories": {name: source_facts(root) for name, root in (
            ("nexus", ROOT), ("connector", args.connector_root), ("core", args.core_root))},
        "collections": {name: {
            **{k: v for k, v in data.items() if k != "nodes"},
            "count": len(data["nodes"]),
            "report_sha256": digest(getattr(args, f"{name}_collection")),
            "command": f"{data['interpreter']} -X utf8 {Path(__file__).with_name('collect_tests.py')} <report.json>",
        } for name, data in collections.items()},
        "tasks": tasks,
        "scenarios": {s["id"]: {
            "task_ids": s["task_ids"], "layer": s["layer"],
            "candidate_nodeids": sorted({node for task in s["task_ids"]
                for node in tasks[task]["collected_nodeids"]}),
            "coverage": "REQUIRES_REVIEW", "execution": "NOT_RUN",
        } for s in matrix["scenarios"]},
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"tasks": len(tasks), "scenarios": len(report["scenarios"]),
                      "availability": dict(Counter(t["test_availability"] for t in tasks.values())),
                      "collection_counts": {name: data["count"] for name, data in report["collections"].items()}}))


if __name__ == "__main__":
    main()
