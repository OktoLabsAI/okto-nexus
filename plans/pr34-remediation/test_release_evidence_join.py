"""Reject misleading joins across incomplete, failed or unqualified campaigns."""
from copy import deepcopy

import pytest

from join_release_evidence import join, native_records


def inputs():
    catalogue = {"requirements": [{"test_id": "T-FIXTURE", "kind": "explicit_test_nodes",
                                  "mappings": [{"nodes": ["tests/test_fixture.py::test_case"]}]}]}
    source = {"release_sha": "release", "qualification_basis": "audited equivalence",
              "original_source_identity": "original base plus diff", "exit_code": 0,
              "evidence_sha256": "fixture", "evidence": "fixture.json", "platform": "windows",
              "records": [{"node": "tests/test_fixture.py::test_case[a]", "status": "PASS"}]}
    return catalogue, source


def test_missing_parameter_cannot_be_hidden_by_other_passing_parameters():
    catalogue, source = inputs()
    source["records"].append({"node": "tests/test_fixture.py::test_case[b]", "status": "SKIP"})
    assert join(catalogue, [source], "release")["counts"] == {"NOT_RUN": 1}


def test_cross_platform_pass_retains_skip_and_does_not_hide_a_failure():
    catalogue, source = inputs()
    other = deepcopy(source)
    other.update(platform="linux", evidence="linux.json")
    source["records"][0]["status"] = "SKIP"
    row = join(catalogue, [source, other], "release")["requirements"][0]
    assert row["execution_status"] == "PASS"
    assert row["mappings"][0]["routes"][0]["observations"][0]["status"] == "SKIP"
    source["records"][0]["status"] = "FAIL"
    assert join(catalogue, [source, other], "release")["counts"] == {"FAIL": 1}


@pytest.mark.parametrize("field,value", [("release_sha", "other"), ("qualification_basis", ""),
                                        ("exit_code", None), ("exit_code", 1),
                                        ("evidence_sha256", ""), ("original_source_identity", "")])
def test_unqualified_evidence_is_rejected(field, value):
    catalogue, source = inputs()
    source[field] = value
    with pytest.raises(ValueError):
        join(catalogue, [source], "release")


def test_platform_specific_route_and_missing_node_are_not_filled_by_other_platform():
    catalogue, source = inputs()
    catalogue["requirements"][0]["mappings"] = [{"platform_nodes": {
        "linux": ["tests/test_fixture.py::test_case[a]"],
        "windows": ["tests/test_fixture.py::test_absent"]}}]
    assert join(catalogue, [source], "release")["counts"] == {"NOT_RUN": 1}


def test_native_call_alone_is_not_pass_and_failed_cleanup_is_failure():
    manifest = {"test_results": [{"test": "native", "phase": "call", "outcome": "passed"}]}
    assert native_records(manifest)[0]["status"] == "NOT_RUN"
    manifest["test_results"].append({"test": "native", "phase": "teardown", "outcome": "failed"})
    assert native_records(manifest)[0]["status"] == "FAIL"
