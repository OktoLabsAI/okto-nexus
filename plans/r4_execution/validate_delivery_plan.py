"""Check delivery coverage and ordering; this does not run product tests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(__file__).resolve().parent


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate() -> dict:
    plan = read_json(FOLDER / "delivery_plan.json")
    sources = {key: ROOT / value for key, value in plan["sources"].items()}
    backlog = read_json(sources["backlog"])
    tests = read_json(sources["tests"])["scenarios"]
    tasks = {task["id"]: task for task in backlog["tasks"]}
    milestones = {item["id"]: item for item in plan["milestones"]}
    require(len(tasks) == len(backlog["tasks"]) == 85,
            "The normative 85-task baseline changed or contains duplicates.")
    require(len(tests) == len({test["id"] for test in tests}) == 164,
            "The normative 164-scenario baseline changed or contains duplicates.")
    require(len(milestones) == len(plan["milestones"]) == 14,
            "Expected 14 distinct delivery milestones.")
    document = (ROOT / plan["document"]).read_text(encoding="utf-8")
    for milestone in milestones:
        require(f"### {milestone} " in document,
                f"Missing documented milestone: {milestone}")

    ancestors: dict[str, set[str]] = {}

    def visit(milestone: str, trail: set[str]) -> set[str]:
        require(milestone in milestones, f"Unknown milestone: {milestone}")
        require(milestone not in trail, f"Milestone dependency cycle: {milestone}")
        if milestone not in ancestors:
            prior: set[str] = set()
            for dependency in milestones[milestone]["depends_on"]:
                prior |= {dependency} | visit(dependency, trail | {milestone})
            ancestors[milestone] = prior
        return ancestors[milestone]

    for milestone in milestones:
        visit(milestone, set())

    task_map: dict[str, str] = {}
    phases = {phase["id"] for phase in backlog["phases"]}
    for milestone in milestones.values():
        require(set(milestone["nexus_phases"]) <= phases,
                f"Unknown phase in {milestone['id']}")
        selected = list(milestone["nexus_tasks"]) + [
            task_id for task_id, task in tasks.items()
            if task["phase_id"] in milestone["nexus_phases"]
        ]
        for task_id in selected:
            require(task_id in tasks, f"Unknown task: {task_id}")
            require(task_id not in task_map, f"Task assigned twice: {task_id}")
            task_map[task_id] = milestone["id"]
    require(set(task_map) == set(tasks), "Some Nexus tasks have no closing milestone.")
    for task_id, task in tasks.items():
        for dependency in task["dependencies"]:
            require(dependency in task_map, f"Unknown task dependency: {dependency}")
            before, after = task_map[dependency], task_map[task_id]
            require(before == after or before in ancestors[after],
                    f"Original task order is not preserved: {dependency} -> {task_id}")

    test_map: dict[str, str] = {}
    for test in tests:
        require(bool(test["task_ids"]), f"Scenario has no task: {test['id']}")
        require(set(test["task_ids"]) <= set(task_map),
                f"Scenario refers to an unknown task: {test['id']}")
        closures = {task_map[task_id] for task_id in test["task_ids"]}
        # Independent workstreams can only be accepted together in M13.
        latest = [item for item in closures
                  if closures - {item} <= ancestors[item]]
        test_map[test["id"]] = latest[0] if len(latest) == 1 else "M13"
    for task in tasks.values():
        require(set(task["test_ids"]) <= set(test_map),
                f"Task refers to an unknown test: {task['id']}")

    external = plan["external_deliverables"]
    handoff = sources["handoff"].read_text(encoding="utf-8")
    expected_external = set(re.findall(r"^### ((?:CORE|CON)-R4-\d{2})", handoff, re.M))
    require(len(external) == len({item["id"] for item in external}) == 12,
            "Expected 12 distinct Core and Connector deliverables.")
    require({item["id"] for item in external} == expected_external,
            "Core or Connector handoff coverage is incomplete.")
    for item in external + plan["additional_requirements"]:
        require(item["close_at"] in milestones, f"Unknown closure for {item['id']}")
        for check in item["verify_again_at"]:
            require(item["close_at"] in ancestors.get(check, set()),
                    f"Verification precedes closure for {item['id']}")
    require(set(plan["cn5_findings"]) == {"Q01", "Q02", "Q03", "Q04"},
            "CN5 findings are not fully mapped.")
    require(set(plan["cn5_findings"].values()) <= set(milestones),
            "Unknown CN5 closing milestone.")

    routes = {row["method"] + " " + row["path"]
              for row in read_json(sources["http_routes"])["routes"]}
    require(set(plan["http_route_closure"]) == routes and len(routes) == 23,
            "The 23 HTTP and WebSocket routes are not fully mapped.")
    require(set(plan["http_route_closure"].values()) <= set(milestones),
            "Unknown route closing milestone.")
    actions = set(read_json(sources["nxl_delta"])["operation_submit"]["payload_definitions"])
    require(set(plan["operation_actions"]) == actions and len(actions) == 7,
            "The seven operation actions are not fully mapped.")
    for action in plan["operation_actions"].values():
        require(set(action) == {"local", "remote", "final_acceptance"} and
                set(action.values()) <= set(milestones),
                "An operation action is missing its local or remote acceptance.")
    language = plan["additional_requirements"]
    require(len(language) == 1 and language[0]["id"] == "LANG-US-01" and
            set(language[0]["tests"]) == {f"TLANG-0{i}" for i in range(1, 5)},
            "US English coverage is incomplete.")
    require(all(test in document for test in language[0]["tests"]),
            "Language scenarios must be described in the delivery document.")

    return {
        "plan_id": plan["plan_id"],
        "validation": "PASS_DOCUMENT_COVERAGE_ONLY",
        "product_tests_executed_by_this_validator": False,
        "source_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"):
                          hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sources.values()},
        "counts": {"milestones": len(milestones), "nexus_tasks": len(task_map),
                   "original_scenarios": len(test_map),
                   "external_deliverables": len(external),
                   "cn5_findings": len(plan["cn5_findings"]),
                   "http_and_websocket_routes": len(routes),
                   "operation_actions": len(actions), "language_scenarios": 4},
        "task_closure": dict(sorted(task_map.items())),
        "scenario_closure": dict(sorted(test_map.items())),
        "external_closure": {item["id"]: item["close_at"] for item in external},
        "final_reassessment": "M13: all applicable scenarios on the immutable release tuple",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    report = validate()
    if args.write_report:
        (FOLDER / "delivery_coverage.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"validation": report["validation"],
                      "counts": report["counts"]}, indent=2))
