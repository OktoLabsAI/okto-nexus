"""Curate the literal installed supplement, including failure/non-execution."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import psutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    gate = read(HERE / "TESTS_READY.json")
    assert sha(HERE / "TESTS_READY.json") == "9399da3f6f3c6bce562b6ef8ba5d6b5b66d864fdeb854abd6af646e78aedbe9c"
    root = Path(read(HERE / "allocation.json")["root"])
    run = read(root / "result.json")
    collected = read(root / "reports/collected.json") if (root / "reports/collected.json").exists() else []
    inventory = read(root / "reports/inventory.json") if (root / "reports/inventory.json").exists() else {"collected": collected, "finished": [], "not_run": collected}
    phases = [json.loads(line) for line in (root / "reports/phases.jsonl").read_text().splitlines()] if (root / "reports/phases.jsonl").exists() else []
    outcomes, nodes = Counter(), []
    for node in collected:
        values = [phase for phase in phases if phase["nodeid"] == node]
        status = "FAIL" if any(v["outcome"] == "failed" for v in values) else "SKIP" if any(v["outcome"] == "skipped" for v in values) else "PASS" if node in inventory["finished"] and any(v["phase"] == "call" and v["outcome"] == "passed" for v in values) else "NOT_RUN"
        outcomes[status] += 1
        nodes.append({"nodeid": node, "status": status,
            "phases": [{k: v for k, v in phase.items() if k != "longrepr"} for phase in values],
            "raw_failure_sha256": [hashlib.sha256(v.get("longrepr", "").encode()).hexdigest() for v in values if v["outcome"] == "failed"]})
    alive = []
    for info in run["known_processes"]:
        try:
            process = psutil.Process(info["pid"])
            if process.create_time() == info["birth"] and process.exe() == info["exe"]:
                alive.append(info)
        except psutil.NoSuchProcess:
            pass
    before, after = read(root / "source-before.json"), read(root / "source-after.json")
    payload_before, payload_after = read(root / "payload-before.json"), read(root / "payload-after.json")
    copies = read(root / "copied-tests.json")
    copied_drift = [name for name, pin in copies.items() if sha(root / "tree" / name) != pin]
    copied_source_mismatch = [name for name, pin in copies.items() if before.get(name.replace("\\", "/")) != pin]
    helpers_before, helpers_after = read(root / "copied-helpers-before.json"), read(root / "copied-helpers-after.json")
    helper_drift = [name for name, value in helpers_after.items() if value["source_sha256"] != helpers_before[name]["source_sha256"] or value["copied_sha256"] != helpers_before[name]["copied_sha256"]]
    assert not (root / "tree/src").exists()
    output = HERE / "evidence"
    assert not output.exists(), "Preserve this cut"
    output.mkdir()
    for name in ("TESTS_READY.json", "result.json", "source-before.json", "source-after.json",
        "payload-before.json", "payload-after.json", "copied-tests.json", "copied-helpers-before.json", "copied-helpers-after.json",
        "reports/collected.json", "reports/inventory.json", "reports/origins-start.json", "reports/origins-end.json"):
        source = root / name
        if source.exists():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    (output / "phase-inventory.json").write_text(json.dumps(nodes, indent=2) + "\n")
    junit = root / "reports/tests.xml"
    errors, seconds = None, None
    if junit.exists():
        xml = ET.parse(junit)
        suites = list(xml.iter("testsuite"))
        errors = sum(int(s.get("errors", "0")) for s in suites)
        seconds = sum(float(s.get("time", "0")) for s in suites)
        for parent in xml.iter():
            for child in list(parent):
                if child.tag in {"system-out", "system-err", "properties"}:
                    parent.remove(child)
                elif child.tag in {"failure", "error", "skipped"}:
                    pin = hashlib.sha256(ET.tostring(child)).hexdigest()
                    child.attrib.clear()
                    child.set("raw_sha256", pin)
                    child.text = "Raw diagnostic retained in owned Temp."
        xml.write(output / "tests-sanitized.xml", encoding="utf-8", xml_declaration=True)
    clean = (run["exit_code"] == 0 and len(collected) == gate["expected_nodes"] == 7 and outcomes == {"PASS": 7}
        and not inventory["not_run"] and errors == 0 and before == after and payload_before == payload_after
        and not any((alive, run["remaining_known_processes"], run["signals"], run["timed_out"], run["forced"],
            copied_drift, copied_source_mismatch, helper_drift, run["source_drift"], run["payload_drift"], run["helper_drift"])))
    report = dict(at=datetime.now(timezone.utc).isoformat(), status="PASS_R7_INSTALLED_SUPPLEMENT" if clean else "NOT_GREEN",
        counts={name: outcomes[name] for name in ("PASS", "SKIP", "FAIL", "NOT_RUN")}, junit_errors=errors, junit_seconds=seconds,
        collected=collected, runtime_source_commit=run["runtime_source_commit"], runtime_wheel_sha256=gate["runtime_wheel_sha256"],
        new_test_file=gate["additions"], expected_base_pins=1828, actual_guarded_pins=len(before), payload_files=len(payload_before),
        source_equal=before == after, payload_equal=payload_before == payload_after, copied_test_files=len(copies),
        copied_test_drift=copied_drift, copied_source_mismatch=copied_source_mismatch, helper_drift=helper_drift,
        process_exit=run["exit_code"], timed_out=run["timed_out"], force_used=run["forced"], signals=run["signals"],
        known_processes=run["known_processes"], known_processes_still_alive=alive, remaining_known_processes=run["remaining_known_processes"],
        stdout={"raw_preserved": str(root / "reports/stdout.log"), "sha256": sha(root / "reports/stdout.log"), "copied": False},
        provider_calls=0, prefix_mutated=False, test_assertions_rewritten=False,
        layers={"A06": "SQLite private-proof/filter component only; no fabricated lease or runtime Working claim",
            "E08_E09": "2 historical receipt/capture SQLite and actual ASGI partial-output cases",
            "E16": "Off-page seen/retention and three same-claim artifact references; no inbox ACK",
            "H02_H03": "HTTP denial/minimization, not DOM/ANSI execution proof",
            "H07": "Canonical native request/HTTP denial; grant revocation is SQL negative fixture, not canonical lifecycle"},
        limits=gate["limits"] + [run["observation_limit"], "Initial source 6 PASS/1 FAIL and corrected source 7 PASS remain separate cuts."])
    (HERE / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    files = {p.relative_to(HERE).as_posix(): sha(p) for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name != "curation-manifest.json"}
    (HERE / "curation-manifest.json").write_text(json.dumps(files, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "counts": report["counts"], "junit_errors": errors,
        "junit_seconds": seconds, "report_sha256": sha(HERE / "qualification.json"), "manifest_sha256": sha(HERE / "curation-manifest.json")}))
    raise SystemExit(0 if clean else 1)


if __name__ == "__main__":
    main()
