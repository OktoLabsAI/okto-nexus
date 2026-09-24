"""Join reviewed requirement coverage to completed, SHA-specific pytest results.

This does not infer coverage from test names or update the execution backlog.
Missing, skipped, or partially reviewed coverage remains NOT_RUN. A matching
failed test remains FAIL even when the rest of a requirement is not covered.
Only sanitized manifests from summarize_pytest_evidence.py are accepted.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def build(backlog, review, manifests):
    sha = review["source_sha"]
    if not manifests or any(manifest["source_sha"] != sha for manifest in manifests):
        raise ValueError("Every execution manifest must match the reviewed source SHA")
    requirements = {row["test_id"]: row for row in backlog["tests"]}
    reviews = review["requirements"]
    if len({row["test_id"] for row in reviews}) != len(reviews):
        raise ValueError("Duplicate requirement review")
    if set(row["test_id"] for row in reviews) - requirements.keys():
        raise ValueError("Review references unknown requirement")
    by_id = {row["test_id"]: row for row in reviews}
    rows = []
    for test_id, requirement in requirements.items():
        reviewed = by_id.get(test_id)
        row = {"test_id": test_id, "name": requirement["name"],
               "status": "NOT_RUN", "coverage_review": "not_reviewed",
               "execution": [], "limitations": "Source coverage has not been reviewed in this audit."}
        if reviewed:
            row["coverage_review"] = reviewed["coverage"]
            row["limitations"] = reviewed["limitations"]
            row["rationale"] = reviewed["rationale"]
            if reviewed["coverage"] not in {"complete", "partial"} or not reviewed["nodes"]:
                raise ValueError("A coverage review needs explicit nodes and complete/partial classification")
            for manifest in manifests:
                for node in reviewed["nodes"]:
                    path, function = node.split("::", 1)
                    class_name = path.removesuffix(".py").replace("/", ".")
                    matches = [record for record in manifest["records"]
                               if record["class"] == class_name and
                               (record["test"] == function or record["test"].startswith(function + "["))]
                    row["execution"].append({"platform": manifest["platform"], "node": node,
                        "results": matches, "missing": not matches})
            statuses = [record["status"] for item in row["execution"] for record in item["results"]]
            if any(status in {"FAIL", "ERROR"} for status in statuses):
                row["status"] = "FAIL"
            elif (reviewed["coverage"] == "complete" and statuses
                  and all(status == "PASS" for status in statuses)
                  and not any(item["missing"] for item in row["execution"])):
                row["status"] = "PASS"
        rows.append(row)
    return {"schema_version": 1, "source_sha": sha,
            "scope": "Reviewed source assertions joined to explicitly supplied completed executions only; no historical totals merged.",
            "counts": dict(Counter(row["status"] for row in rows)),
            "platforms": [manifest["platform"] for manifest in manifests], "requirements": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backlog", type=Path, default=Path("05_BACKLOG.json"))
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))
    result = build(read(args.backlog), read(args.review), [read(path) for path in args.manifest])
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"]))


if __name__ == "__main__":
    main()
