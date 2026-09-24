"""Evidence integrity checks; no providers, secrets, sockets or subprocesses."""
from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pytest

from build_matrix_evidence import build
from native_frame_campaign import FrameRecorder


def inputs():
    backlog = {"tests": [{"test_id": "T-ID-01", "name": "fixture"}]}
    review = {"source_sha": "fixture-sha", "requirements": [{"test_id": "T-ID-01",
        "coverage": "complete", "nodes": ["tests/test_fixture.py::test_behavior"],
        "limitations": "Fixture", "rationale": "Reviewed assertions"}]}
    manifest = {"source_sha": "fixture-sha", "platform": "fixture",
        "records": [{"class": "tests.test_fixture", "test": "test_behavior[a]", "status": "PASS"}]}
    return backlog, review, manifest


@pytest.mark.parametrize("status,expected", [("PASS", "PASS"), ("SKIP", "NOT_RUN"),
    ("ERROR", "FAIL"), ("FAIL", "FAIL"), ("unknown", "NOT_RUN")])
def test_matrix_uses_observed_status_without_promoting_skips(status, expected):
    backlog, review, manifest = inputs()
    manifest["records"][0]["status"] = status
    assert build(backlog, review, [manifest])["requirements"][0]["status"] == expected


def test_matrix_rejects_mixed_sha_and_requires_all_parameterized_results():
    backlog, review, manifest = inputs()
    other = deepcopy(manifest)
    other["source_sha"] = "other-sha"
    with pytest.raises(ValueError, match="SHA"):
        build(backlog, review, [manifest, other])
    other = deepcopy(manifest["records"][0])
    other.update(test="test_behavior[b]", status="SKIP")
    manifest["records"].append(other)
    assert build(backlog, review, [manifest])["counts"] == {"NOT_RUN": 1}


def test_partial_or_missing_coverage_is_not_pass():
    backlog, review, manifest = inputs()
    review["requirements"][0]["coverage"] = "partial"
    assert build(backlog, review, [manifest])["counts"] == {"NOT_RUN": 1}
    review["requirements"][0]["coverage"] = "complete"
    manifest["records"] = []
    assert build(backlog, review, [manifest])["requirements"][0]["execution"][0]["missing"]
    assert build(backlog, review, [manifest])["counts"] == {"NOT_RUN": 1}


def test_behavioral_audit_failure_overrides_a_green_selected_suite():
    backlog, review, manifest = inputs()
    observation = {"source_sha": "fixture-sha", "test_id": "T-ID-01", "status": "FAIL"}
    assert build(backlog, review, [manifest], [observation])["counts"] == {"FAIL": 1}
    with pytest.raises(ValueError, match="SHA"):
        build(backlog, review, [manifest], [observation | {"source_sha": "other-sha"}])


def test_frames_never_persist_body_or_arbitrary_protocol_labels():
    recorder = FrameRecorder()
    secret = "fixture-sensitive-string"
    recorder.record("codex", "out", {"method": "turn/start", "id": secret,
        "params": {"threadId": secret, "text": secret}}, peer=1)
    recorder.record("codex", "in", {"method": secret, "params": {"text": secret}}, peer=1)
    recorder.record("claude_code", "in", {"type": "control_request",
        "request_id": secret, "request": {"subtype": secret, "input": secret}}, peer=2)
    assert secret not in json.dumps(recorder.frames)
    assert recorder.frames[1]["name"] == "other_native_method"
    assert recorder.frames[2]["name"] == "unclassified"


def test_frame_boundaries_preserve_io_and_correlate_reply_without_raw_ids():
    recorder = FrameRecorder()
    stream = io.StringIO('{"id":"fixture-id","result":{}}\n')
    peer = SimpleNamespace(_proc=SimpleNamespace(stdout=stream))
    writes = []
    write = recorder.writer("codex", lambda peer, payload: writes.append(payload))
    payload = {"method": "initialize", "id": "fixture-id"}
    write(peer, payload)
    lines = list(recorder.reader("codex", iter)(stream))
    assert writes == [payload] and json.loads(lines[0])["id"] == "fixture-id"
    outgoing, incoming = recorder.frames
    assert outgoing["peer_alias"] == incoming["peer_alias"]
    assert outgoing["request_alias"] == incoming["request_alias"]
    assert outgoing["boundary"] == "write_returned"
    assert "fixture-id" not in json.dumps(recorder.frames)


@pytest.mark.parametrize("method", ["thread/read", "unknown/method"])
def test_status_queries_and_unclassified_outbound_frames_fail_qualification(method):
    recorder = FrameRecorder()
    recorder.test_results = [{"phase": "call", "outcome": "passed"}]
    recorder.record("codex", "out", {"method": method}, peer=1)
    recorder.record("codex", "in", {"id": 1, "result": {}}, peer=1)
    assert not recorder.qualification(0)


def test_recording_overflow_cannot_be_reported_as_complete_trace():
    recorder = FrameRecorder(limit=1)
    recorder.record("codex", "out", {"method": "turn/start"}, peer=1)
    recorder.record("codex", "in", {"method": "turn/completed"}, peer=1)
    assert len(recorder.frames) == 1 and recorder.overflow
    assert not recorder.qualification(0)


def test_unexecuted_native_cases_remain_not_run():
    recorder = FrameRecorder()
    assert recorder.status(5) == "NOT_RUN"
    recorder.test_results = [{"phase": "setup", "outcome": "skipped"}]
    assert recorder.status(0) == "NOT_RUN"
    recorder.test_results.append({"phase": "setup", "outcome": "failed"})
    assert recorder.status(1) == "FAIL"


def test_failed_native_write_retains_uncertainty_and_exception():
    recorder = FrameRecorder()
    def failed(peer, payload):
        raise OSError("fixture failure")
    with pytest.raises(OSError, match="fixture failure"):
        recorder.writer("codex", failed)(object(), {"method": "turn/start"})
    assert recorder.frames[0]["boundary"] == "write_failed_or_uncertain"


def test_protocol_model_observations_are_explicit_and_do_not_include_arbitrary_labels():
    recorder = FrameRecorder()
    recorder.record("codex", "in", {"id": 1, "result": {"model": "gpt-5.3-codex",
        "thread": {"modelProvider": "openai"}}}, peer=1)
    recorder.record("claude_code", "in", {"type": "system", "model": "claude-opus-4-6"}, peer=2)
    recorder.record("codex", "in", {"result": {"model": "fixture-private-model-secret",
        "modelProvider": "fixture-private-provider-secret"}}, peer=1)
    labels = json.dumps(recorder.backend_observations)
    assert "gpt-5.3-codex" in labels and "claude-opus-4-6" in labels and "openai" in labels
    assert "fixture-private" not in labels
