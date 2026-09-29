"""Executable baseline and crosswalk checks for the R4 plan."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / "plans"


def _git(*args: str) -> bytes:
    return subprocess.check_output(("git", *args), cwd=ROOT)


def test_ns00_01():
    baseline = json.loads((PLANS / "r4_execution/baseline.json").read_text())
    source = baseline["source"]
    assert _git("branch", "--show-current").decode().strip() == "feature/v0.2.0"
    subprocess.run(("git", "merge-base", "--is-ancestor",
                    source["head_at_start"], "HEAD"), cwd=ROOT, check=True)
    for path, expected in source["head_file_sha256"].items():
        original = _git("show", f"{source['head_at_start']}:{path}")
        assert hashlib.sha256(original).hexdigest() == expected
    assert baseline["core"]["head_at_start"]
    assert baseline["connector"]["head_at_start"]
    assert baseline["core"]["nxl_revision_at_start"].endswith("-r3")
    assert baseline["core"]["provider_qualified_by_this_work"] is False


def test_ns00_02():
    active = json.loads((PLANS / "r4_execution/ACTIVE_PLAN.json").read_text())
    crosswalk = (PLANS / "07_RASTREABILIDADE_R3.md").read_text(encoding="utf-8")
    backlog = json.loads((PLANS / "BACKLOG_R4.json").read_text(encoding="utf-8"))
    matrix = json.loads((PLANS / "MATRIZ_TESTES_R4.json").read_text(encoding="utf-8"))
    original = re.findall(r"^\| (N\d{2}\.\d) \|.*\| (NS[^|]+) \|$",
                          crosswalk, flags=re.MULTILINE)
    tasks = {task["id"] for task in backlog["tasks"]}
    assert len(original) == 70
    assert all(set(re.findall(r"NS\d{2}\.\d{2}", targets)) <= tasks
               for _, targets in original)
    ids = {scenario["id"] for scenario in matrix["scenarios"]}
    assert sum(bool(re.fullmatch(r"TN-\d{2}", item)) for item in ids) == 45
    assert sum(bool(re.fullmatch(r"J\d{2}", item)) for item in ids) == 34
    assert active["active_backlog"] == "plans/BACKLOG_R4.json"
    assert active["legacy_plans"].startswith("superseded")
