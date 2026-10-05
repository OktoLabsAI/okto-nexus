"""Executable baseline and crosswalk checks for the R4 plan."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nexus_connector_core.models import CoreError
from nexus_connector_core.frame_codec import decode_frame
from nexus_connector_core.protocol import canonical_json
from nexus_connector_core.protocol import CONTRACT_REVISION, require_contract
from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap

from lab_peer import CausalPeer

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


def test_ns00_03(tmp_path):
    """Direct R4 representation cannot be interpreted as legacy or r3 wire."""
    adr = (ROOT / "docs/adr/0001-r4-authority-and-wire.md").read_text(encoding="utf-8")
    assert "nexus-connector-core" in adr
    assert "X-Nexus-Connections-Revision" in adr
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    with TestClient(build_app(deps)) as client:
        direct = client.get("/v1/connections/protocol")
        legacy = client.get("/api/v1/info")
    assert direct.status_code == legacy.status_code == 200
    assert "ok" not in direct.json()
    assert legacy.json()["ok"] is True
    assert "data" in legacy.json()
    assert direct.headers["X-Nexus-Connections-Revision"] == (
        "nexus-connections-2026-09-29-r4"
    )
    assert CONTRACT_REVISION.endswith("-r3")
    with pytest.raises(CoreError) as incompatible:
        require_contract(1, "nxl-1-agent-centric-http-only-2026-09-29-r4")
    assert incompatible.value.code == "VERSION_INCOMPATIBLE"


def test_ns00_04():
    """The installed r3 codec keeps historical receipts and fences r4 bytes."""
    resource = importlib.resources.files("nexus_connector_core.contracts.nxl.v1")
    fixtures = json.loads(resource.joinpath("fixtures.json").read_text(encoding="utf-8"))
    historical = next(frame for frame in fixtures["frames"]["valid"]
                      if frame["type"] == "operation.receipt")
    assert decode_frame(canonical_json(historical)) == historical
    changed = {**historical,
               "contract_revision": "nxl-1-agent-centric-http-only-2026-09-29-r4"}
    with pytest.raises(CoreError) as incompatible:
        decode_frame(canonical_json(changed))
    assert incompatible.value.code == "VERSION_INCOMPATIBLE"


def test_ns00_05():
    """Lab peer models a lost reply, with provider/multi-host gates still open."""
    manifest = json.loads((PLANS / "r4_execution/evidence_manifest.json").read_text())
    assert manifest["layers"]["provider"] == "NOT_RUN"
    assert manifest["layers"]["two_hosts"] == "NOT_RUN"
    assert all(state == "OPEN" for state in manifest["gates"].values())
    assert all(item["exit_code"] == 0 and item["command"]
               for item in manifest["evidence"])
    peer = CausalPeer()
    peer.drop_next_reply = True
    assert peer.submit("op-a", "sha256:original") is None
    receipt = peer.query("op-a")
    assert receipt is not None and receipt.possible_effect
    assert peer.submit("op-a", "sha256:original") == receipt
    assert peer.effect_count == 1
    with pytest.raises(ValueError):
        peer.submit("op-a", "sha256:changed")
