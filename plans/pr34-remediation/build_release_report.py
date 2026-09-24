"""Generate the final scoped report from reviewed routes and observed results.

Run from the repository root. This writes a report, never changes backlog status,
never treats fixture evidence as native evidence, and never hides historical scope.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("execution_join", type=Path)
    parser.add_argument("separate_assessments", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    observed = read(args.execution_join)
    separate = read(args.separate_assessments)
    backlog = read("05_BACKLOG.json")
    original = {row["test_id"]: row for row in backlog["tests"]}
    joined = {row["test_id"]: row for row in observed["requirements"]}
    assert len(original) == len(backlog["tests"]) == 129
    assert len(joined) == len(observed["requirements"]) == 129
    assert set(original) == set(joined)
    assert observed["release_sha"] == backlog["execution_head"]
    assert digest(observed["recipe"]) == observed["recipe_sha256"]
    recipe = read(observed["recipe"])
    assert recipe["release_sha"] == observed["release_sha"]
    assert digest(recipe["catalogue"]) == observed["catalogue_sha256"]
    for source in observed["sources"]:
        assert digest(source["evidence"]) == source["evidence_sha256"]
        assert source["exit_code"] == 0 and source["qualification_basis"]
        assert source["original_source_identity"]
    prefix = Path("plans/pr34-remediation/evidence")
    windows = read(prefix / "p12-full-corrected-windows.json")
    linux = read(prefix / "p12-full-corrected-linux.json")
    for suite in (windows, linux):
        assert suite["status"] == "TERMINAL" and suite["exit_code"] == 0
        assert not (set(suite["counts"]) - {"PASS", "SKIP"})
    assert linux["source_sha"] == observed["release_sha"]
    assert windows["qualified_implementation_sha"] == observed["release_sha"]
    equivalence = read(windows["source_equivalence"])
    assert equivalence["integrated_commit"] == observed["release_sha"]
    assert equivalence["source_equivalent_after_explicit_crlf_normalization"]
    assert not equivalence["other_differences"]
    integrity = read(prefix / "p12-windows-post-run-integrity.json")
    assert integrity["status"] == "PASS" and not integrity["changed_since_launch"]
    assert integrity["tracked_source_files_rechecked"] == equivalence["compared_tracked_files"]
    assert windows["dirty_diff_sha256"] == equivalence["candidate_dirty_diff_sha256"]
    for name in ("p12-native-ff905c4-codex.json", "p12-native-ff905c4-claude_code.json"):
        native = read(prefix / name)
        assert native["source_sha"] == observed["release_sha"]
        assert native["status"] == "PASS" and native["pytest_exit_code"] == 0
        assert native["frames"] and not native["overflow"]
        assert not native["outbound_categories"].get("status_query", 0)
        assert not native["outbound_categories"].get("unclassified", 0)
    installed = read(prefix / "p12-installed-release-ff905c4.json")
    assert installed["status"] == "PASS" and installed["installed_version"] == "0.2.0"
    assert installed["source_sha"] == observed["release_sha"]
    assert installed["smoke"]["status"] == "PASS"
    rows = []
    report_checks = [
        "All129 original requirement IDs present exactly once",
        "Recipe, catalogue and every execution source retain verified digests",
        "Both full suites observed terminal exit0; skips retained",
        "Original Windows base/diff identity and CRLF-only equivalence retained",
        "Post-terminal Windows tracked source unchanged; Linux exact committed SHA",
        "Approved native source identities and installed0.2.0 source agree",
        "Every parameter/platform observation retained; historical load sources labeled",
        "Pi and dedicated attach native exclusions remain NOT_RUN",
        "Finding code hashes read from the implementation commit, not local generated assets",
    ]
    assert set(separate) == {r["test_id"] for r in joined.values()
                            if r["kind"] == "separate_campaign_or_report"}
    for test_id, requirement in original.items():
        route = joined[test_id]
        if test_id == "T-E2E-07":
            result = {"status": "PASS", "evidence": [str(args.output).replace("\\", "/")],
                      "scope": "This generated report passed its listed source/result integrity checks."}
        elif route["kind"] == "separate_campaign_or_report":
            result = separate[test_id]
        else:
            state = route["execution_status"]
            # A green execution join does not replace the separate behavioral review.
            if state == "PASS" and requirement["execution_status"] != "PASS":
                state = "NOT_RUN"
            result = {"status": state, "evidence": requirement["evidence"],
                      "scope": "Current-source execution joined to the reviewed assertion routes; platform skips, native/UI separation and original partial classifications remain explicit in the join.",
                      "historical_acceptance_notes": requirement.get("notes", ""),
                      "execution_join": str(args.execution_join).replace("\\", "/")}
        assert result["status"] in {"PASS", "FAIL", "NOT_RUN", "NOT_APPLICABLE"}
        for reference in result["evidence"]:
            if test_id != "T-E2E-07":
                assert Path(reference.split("::", 1)[0]).exists(), reference
        rows.append({"test_id": test_id, "name": requirement["name"], **result})
    external = {row["test_id"]: row["status"] for row in rows if row["test_id"] in {"T-E2E-01", "T-E2E-02"}}
    assert external == {"T-E2E-01": "NOT_RUN", "T-E2E-02": "NOT_RUN"}
    old_findings = read(prefix / "p12-final-audit-39c5e6c.json")
    findings = []
    for finding in old_findings["findings"]:
        content = subprocess.check_output(["git", "show", observed["release_sha"] + ":" + finding["code"]])
        for reference in finding["evidence"]:
            assert Path(reference).exists(), reference
        findings.append({**finding, "source_file_sha256": hashlib.sha256(content).hexdigest(),
                         "hash_basis": "Exact Git blob bytes at implementation SHA",
                         "status": "IMPLEMENTED_WITH_RECORDED_QUALIFICATION_SCOPE"})
    assert len(findings) == 15
    counts = dict(Counter(row["status"] for row in rows))
    report = {
        "source_sha": observed["release_sha"], "version": "0.2.0", "branch": "feature/v0.2.0",
        "status": "SCOPED_REPORT_GENERATED", "counts": counts,
        "full_suite_results": {"windows": windows["counts"], "linux": linux["counts"]},
        "report_checks": report_checks, "execution_join": str(args.execution_join).replace("\\", "/"),
        "execution_join_sha256": digest(args.execution_join),
        "separate_assessments": str(args.separate_assessments).replace("\\", "/"),
        "separate_assessments_sha256": digest(args.separate_assessments),
        "generator_sha256": digest(__file__), "findings": findings, "requirements": rows,
        "unrestricted_four_native_gate": "NOT_PASSED: Pi and dedicated Claude attach NOT_RUN",
        "merge_performed": False,
        "limitations": ["Scoped PASS is not universal native/platform qualification.",
                        "Existing load campaigns retain their original generation; counts are not added to current full suites.",
                        "Native/UI campaigns are separate from default-suite skips.",
                        "Current report integrity does not turn old partial behavioral mappings into complete coverage."],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert read(args.output)["counts"] == counts
    print(json.dumps({"requirements": len(rows), "findings": len(findings), "counts": counts}))


if __name__ == "__main__":
    main()
