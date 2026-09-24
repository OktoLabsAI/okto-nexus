"""Reduce completed JUnit output to test identities/results, without captured logs."""
import json
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import Counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("sha")
    parser.add_argument("platform")
    parser.add_argument("output")
    parser.add_argument("--limitations", default="Suite elapsed time is not a performance benchmark. SKIP is not PASS.")
    args = parser.parse_args()
    root = ET.parse(args.source).getroot()
    records = []
    for case in root.iter("testcase"):
        status = "ERROR" if case.find("error") is not None else (
            "FAIL" if case.find("failure") is not None else (
                "SKIP" if case.find("skipped") is not None else "PASS"))
        records.append({"class": case.get("classname", ""), "test": case.get("name"),
            "status": status, "seconds": float(case.get("time", "0"))})
    result = {"source_sha": args.sha, "platform": args.platform, "counts": dict(Counter(row["status"] for row in records)),
        "suites": [{key: value for key, value in suite.attrib.items() if key != "hostname"}
            for suite in root.iter("testsuite")],
        "native_flags": "explicit campaign empty; legacy live flags and UI campaign zero",
        "command": "python -m pytest -q --tb=short --junitxml=<unique-temporary-results.xml>",
        "limitations": args.limitations,
        "records": records}
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"]))


if __name__ == "__main__":
    main()
