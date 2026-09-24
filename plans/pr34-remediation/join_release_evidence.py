"""Join reviewed requirement nodes to explicitly qualified release observations.

This does not promote backlog acceptance. Source equivalence and behavioral scope
must be reviewed separately; skipped platforms remain visible in every result.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def junit_records(manifest):
    return [{"node": row["class"].replace(".", "/") + ".py::" + row["test"],
             "status": row["status"]} for row in manifest["records"]]


def native_records(manifest):
    grouped = defaultdict(dict)
    for row in manifest["test_results"]:
        if row["phase"] in grouped[row["test"]]:
            raise ValueError("Duplicate native phase")
        grouped[row["test"]][row["phase"]] = row["outcome"]
    return [{"node": node, "status": (
        "FAIL" if "failed" in phases.values() else
        "PASS" if phases == dict.fromkeys(("setup", "call", "teardown"), "passed")
        else "NOT_RUN")} for node, phases in grouped.items()]


def matches(requested, observed):
    return requested == observed or ("[" not in requested and observed.startswith(requested + "["))


def status_of(statuses):
    if any(status in {"FAIL", "ERROR"} for status in statuses):
        return "FAIL"
    return "PASS" if "PASS" in statuses else "NOT_RUN"


def join(catalogue, sources, release_sha):
    """Sources carry original identity plus an explicit separately audited basis."""
    for source in sources:
        if source["release_sha"] != release_sha or not source.get("qualification_basis"):
            raise ValueError("Missing release source qualification")
        if source.get("exit_code") != 0:
            raise ValueError("Nonterminal or failed campaign")
        if not source.get("evidence_sha256") or not source.get("original_source_identity"):
            raise ValueError("Missing evidence integrity or original identity")
    rows = []
    for requirement in catalogue["requirements"]:
        row = {"test_id": requirement["test_id"], "kind": requirement["kind"],
               "mappings": [], "scope": "Execution join only; preserve assertion-review limitations."}
        if requirement["kind"] != "explicit_test_nodes":
            row.update(execution_status="SEPARATE_EVIDENCE_REQUIRED",
                       evidence=requirement.get("evidence", []))
            rows.append(row)
            continue
        for mapping in requirement["mappings"]:
            routes = [(None, node) for node in mapping.get("nodes", [])]
            routes += [(platform, node) for platform, nodes in mapping.get("platform_nodes", {}).items()
                       for node in nodes]
            result = {key: value for key, value in mapping.items() if key not in {"nodes", "platform_nodes"}}
            result["routes"] = []
            for platform, requested in routes:
                observations = [{"evidence": source["evidence"], "platform": source["platform"], **record}
                                for source in sources if platform is None or platform == source["platform"]
                                for record in source["records"] if matches(requested, record["node"])]
                variants = sorted({record["node"] for record in observations})
                variants_status = {node: status_of([o["status"] for o in observations if o["node"] == node])
                                   for node in variants}
                state = ("FAIL" if "FAIL" in variants_status.values() else
                         "PASS" if variants_status and all(s == "PASS" for s in variants_status.values())
                         else "NOT_RUN")
                result["routes"].append({"requested": requested, "platform_scope": platform,
                                         "execution_status": state, "variants": variants_status,
                                         "observations": observations})
            row["mappings"].append(result)
        states = [route["execution_status"] for m in row["mappings"] for route in m["routes"]]
        row["execution_status"] = ("FAIL" if "FAIL" in states else
                                   "PASS" if states and all(s == "PASS" for s in states) else "NOT_RUN")
        rows.append(row)
    return {"release_sha": release_sha, "status": "EXECUTION_JOIN_ONLY",
            "counts": dict(Counter(r["execution_status"] for r in rows)),
            "sources": [{k: v for k, v in source.items() if k != "records"} for source in sources],
            "requirements": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
    catalogue_path = Path(recipe["catalogue"])
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(catalogue_path.read_bytes()).hexdigest() == recipe["catalogue_sha256"]
    sources = []
    for entry in recipe["sources"]:
        path = Path(entry["evidence"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["evidence_sha256"]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        records = native_records(manifest) if entry["format"] == "native" else junit_records(manifest)
        sources.append({**entry, "records": records})
    report = join(catalogue, sources, recipe["release_sha"])
    report["recipe"] = str(args.recipe).replace("\\", "/")
    report["recipe_sha256"] = hashlib.sha256(args.recipe.read_bytes()).hexdigest()
    report["catalogue_sha256"] = recipe["catalogue_sha256"]
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"]))


if __name__ == "__main__":
    main()
