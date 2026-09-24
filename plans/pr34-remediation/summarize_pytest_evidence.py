"""Reduce completed JUnit output to test identities/results, without captured logs."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from collections import Counter


def main():
    source, sha, platform, output = sys.argv[1:]
    root = ET.parse(source).getroot()
    records = []
    for case in root.iter("testcase"):
        status = "ERROR" if case.find("error") is not None else (
            "FAIL" if case.find("failure") is not None else (
                "SKIP" if case.find("skipped") is not None else "PASS"))
        records.append({"class": case.get("classname", ""), "test": case.get("name"),
            "status": status, "seconds": float(case.get("time", "0"))})
    result = {"source_sha": sha, "platform": platform, "counts": dict(Counter(row["status"] for row in records)),
        "suites": [{key: value for key, value in suite.attrib.items() if key != "hostname"}
            for suite in root.iter("testsuite")],
        "native_flags": "explicit campaign empty; legacy live flags and UI campaign zero",
        "command": "python -m pytest -q --tb=short --junitxml=<unique-temporary-results.xml>",
        "limitations": "Concurrent platform suites on one physical host; elapsed times are not benchmarks. SKIP is not PASS.",
        "records": records}
    Path(output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"]))


if __name__ == "__main__":
    main()
