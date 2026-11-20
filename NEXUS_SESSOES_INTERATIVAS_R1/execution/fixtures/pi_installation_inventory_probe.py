"""Compare the reviewed and selected Pi artifacts without launching either."""

import json
import sys
from pathlib import Path

from nexus_connector_core.discovery import candidate_pi_node_cli
from nexus_connector_core.executor_inventory import (
    build_executor_inventory_snapshot,
    verify_executor_inventory_snapshot,
)
from nexus_connector_core.pi_extension_resource import reviewed_pi_renderer_build

node, installed, output = map(Path, sys.argv[1:])
version = (installed / "current-version").read_text().strip()
assert version == "1.5.2"
known, current = [
    candidate_pi_node_cli(
        node,
        installed
        / "releases"
        / v
        / "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js",
        explicit=True,
    )
    for v in ("0.87.1", version)
]
assert [row.version for row in (known, current)] == ["0.87.1", "1.5.2"]
snapshot = build_executor_inventory_snapshot(
    [known, current],
    server_id="srv_si_i06",
    executor_id="exe_si_i06",
    producer_instance_id="inventory-si-i06",
    publication_sequence=1,
)
verify_executor_inventory_snapshot(snapshot)
results = []
for candidate in (known, current):
    (evidence,) = [
        item for item in snapshot["evidence"] if item["version"] == candidate.version
    ]
    (row,) = [
        item
        for item in snapshot["availability"]["availability"]
        if item["version"] == candidate.version
    ]
    results.append(
        {
            "version": candidate.version,
            "architecture": candidate.architecture,
            "build_identity": candidate.build_identity,
            "outcome": row["state"],
            "qualification": row["qualification"],
            "controls": evidence["qualified_control_actions"],
            "reasons": row["reasons"],
            "reviewed_native_renderer": reviewed_pi_renderer_build(
                candidate.version,
                sys.platform,
                candidate.architecture,
                candidate.build_identity,
            ),
        }
    )
assert (
    results[0]["reviewed_native_renderer"]
    and results[0]["qualification"] == "qualified"
), results
assert (
    not results[1]["reviewed_native_renderer"]
    and results[1]["qualification"] == "unqualified"
    and not results[1]["controls"]
), results
report = {
    "selected_installation_version": version,
    "inventory_revision": snapshot["inventory_revision"],
    "cases": results,
    "core_validation": "PASS",
    "harness_execution_requested": False,
    "provider_calls": 0,
}
output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
