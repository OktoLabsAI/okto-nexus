"""Synthetic pure comparisons only: no live Core, process or Herdr qualification."""
from copy import deepcopy
import hashlib
import json

import pytest

from okto_nexus.domain.observation_correlation import (
    ObservationCorrelationError, correlation_digest, fences_match, normalize_evidence,
    normalize_selection, verify_native_birth,
)


def selection():
    return dict(source_id="obs_source_a", source_revision=2, observed_instance_id="obs_inst_a", generation=3,
                server_id="server-a", executor_id="executor-a", session_id="session-a", open_operation_id="open-a",
                session_owner_generation=4, stream_epoch="stream-a", binding_id="binding-a",
                workspace_binding_id="workspace-binding-a", expected_correlation_revision=0)


def identity():
    return dict(host_id="a" * 64, pid=123, creation_filetime=134384870609652051,
                image_path=r"C:\Approved Fixture\Native.exe")


def evidence():
    return dict(kind="local_windows_process_v1", **identity(), binding_hash="sha256:" + "b" * 64)


def native_record():
    chosen = selection()
    return dict(server_id=chosen["server_id"], executor_id=chosen["executor_id"], session_id=chosen["session_id"],
                opening_operation_id=chosen["open_operation_id"], platform="win32", pid=identity()["pid"],
                birth_token=f'filetime:{identity()["creation_filetime"]:016x}')


def proof():
    return verify_native_birth(selection(), evidence(), native_record=native_record(), os_identity=identity())


def test_exact_native_birth_proof_is_detached_minimal_and_does_not_claim_liveness():
    selected, external, record, observed = selection(), evidence(), native_record(), identity()
    original = deepcopy((selected, external, record, observed))
    verified = verify_native_birth(selected, external, native_record=record, os_identity=observed)
    assert (selected, external, record, observed) == original
    assert verified == dict(kind="local_windows_process_v1",
        external_binding_provenance="operator_attested_external_binding",
        native_birth_provenance="machine_checked_native_birth", host_id="a" * 64, pid=123,
        creation_filetime=observed["creation_filetime"], binding_hash=external["binding_hash"],
        image_path_sha256="sha256:" + hashlib.sha256(r"c:\approved fixture\native.exe".encode()).hexdigest())
    assert "Approved Fixture" not in json.dumps(verified)
    assert not {"image_path", "container_id", "alive", "ownership", "authorized"} & set(verified)
    selected["generation"] += 1
    assert verified == proof()


@pytest.mark.parametrize("field", tuple(selection()))
def test_each_selected_fence_changes_digest_and_invalidates_without_remapping(field):
    old = selection()
    current = deepcopy(old)
    current[field] = current[field] + 1 if type(current[field]) is int else current[field] + "-changed"
    assert fences_match(old, old)
    assert not fences_match(old, current)
    assert correlation_digest(old, proof()) != correlation_digest(current, proof())
    assert old == selection()


def test_missing_current_record_never_matches():
    assert not fences_match(selection(), None)
    with pytest.raises(ObservationCorrelationError):
        fences_match(selection(), {"session_id": "session-a"})


@pytest.mark.parametrize("field", ["server_id", "executor_id", "session_id", "opening_operation_id", "pid", "birth_token"])
def test_native_namespace_opening_and_birth_must_all_match(field):
    record = native_record()
    record[field] = (124 if field == "pid" else "filetime:0000000000000001" if field == "birth_token"
                     else "different")
    with pytest.raises(ObservationCorrelationError) as caught:
        verify_native_birth(selection(), evidence(), native_record=record, os_identity=identity())
    assert caught.value.code == "OBSERVATION_CORRELATION_PROOF_MISMATCH"


@pytest.mark.parametrize("field,value", [
    ("host_id", "c" * 64), ("pid", 124), ("creation_filetime", 1), ("image_path", r"C:\other\native.exe"),
])
def test_observed_os_identity_must_match_the_operator_selected_identity(field, value):
    observed = identity()
    observed[field] = value
    with pytest.raises(ObservationCorrelationError) as caught:
        verify_native_birth(selection(), evidence(), native_record=native_record(), os_identity=observed)
    assert caught.value.code == "OBSERVATION_CORRELATION_PROOF_MISMATCH"


@pytest.mark.parametrize("path", [r"C:/Approved Fixture/Native.exe", r"\\?\C:\Approved Fixture\Native.exe",
                                  r"c:\approved fixture\native.exe"])
def test_windows_image_spellings_normalize_without_filesystem_access(path):
    external = evidence()
    external["image_path"] = path
    assert normalize_evidence(external)["image_path"] == r"c:\approved fixture\native.exe"
    assert verify_native_birth(selection(), external, native_record=native_record(), os_identity=identity()) == proof()


@pytest.mark.parametrize("path", ["native.exe", r"C:native.exe", r"\native.exe", r"\\host\share\native.exe",
                                  r"\\?\UNC\host\share\native.exe", r"\\.\pipe\native", r"C:\native.exe:stream",
                                  "C:\\", "C:/folder/../", r"C:\bad?\native.exe", "C:\\bad\nname.exe"])
def test_nonlocal_relative_device_and_malformed_paths_are_refused(path):
    external = evidence()
    external["image_path"] = path
    with pytest.raises(ObservationCorrelationError):
        normalize_evidence(external)


@pytest.mark.parametrize("field,value", [
    ("source_revision", True), ("generation", False), ("session_owner_generation", 0),
    ("expected_correlation_revision", -1), ("expected_correlation_revision", True),
    ("source_revision", 1 << 63), ("generation", 1.0), ("stream_epoch", None),
    ("session_id", ""), ("executor_id", "x" * 161), ("server_id", " leading"),
    ("binding_id", "bad\x00id"), ("workspace_binding_id", "\ud800"), ("source_id", "source/path"),
])
def test_strict_selection_types_bounds_and_identifiers(field, value):
    chosen = selection()
    chosen[field] = value
    with pytest.raises(ObservationCorrelationError):
        normalize_selection(chosen)


@pytest.mark.parametrize("field,value", [
    ("kind", "other"), ("host_id", "a" * 63), ("host_id", "A" * 64),
    ("pid", True), ("pid", 0), ("pid", 1 << 32), ("creation_filetime", False),
    ("creation_filetime", 0), ("creation_filetime", 1 << 63), ("creation_filetime", 1.0),
    ("binding_hash", "b" * 64), ("binding_hash", "sha256:" + "g" * 64),
])
def test_strict_evidence_types_hashes_and_integer_bounds(field, value):
    external = evidence()
    external[field] = value
    with pytest.raises(ObservationCorrelationError):
        normalize_evidence(external)


@pytest.mark.parametrize("field,value", [
    ("platform", "linux"), ("pid", True), ("birth_token", "filetime:1"),
    ("birth_token", "filetime:0000000000000000"), ("birth_token", "filetime:8000000000000000"),
    ("birth_token", "filetime:FFFFFFFFFFFFFFFF"), ("birth_token", 123),
])
def test_native_record_is_a_closed_typed_projection(field, value):
    record = native_record()
    record[field] = value
    with pytest.raises(ObservationCorrelationError):
        verify_native_birth(selection(), evidence(), native_record=record, os_identity=identity())


@pytest.mark.parametrize("location", ["selection", "evidence", "record", "os", "proof"])
def test_unexpected_fields_including_secrets_are_rejected_without_echo(location):
    chosen, external, record, observed, verified = selection(), evidence(), native_record(), identity(), proof()
    target = dict(selection=chosen, evidence=external, record=record, os=observed, proof=verified)[location]
    target["PRIVATE_UNKNOWN_FIELD"] = "PRIVATE_SENTINEL_VALUE"
    with pytest.raises(ObservationCorrelationError) as caught:
        if location == "proof":
            correlation_digest(chosen, verified)
        else:
            verify_native_birth(chosen, external, native_record=record, os_identity=observed)
    assert str(caught.value) == "Observation correlation unavailable: OBSERVATION_CORRELATION_INVALID"
    assert "PRIVATE" not in repr(caught.value)


@pytest.mark.parametrize("location,field", [
    ("selection", "stream_epoch"), ("evidence", "binding_hash"),
    ("record", "opening_operation_id"), ("os", "host_id"), ("proof", "native_birth_provenance"),
])
def test_missing_evidence_and_fences_never_default_or_remap(location, field):
    chosen, external, record, observed, verified = selection(), evidence(), native_record(), identity(), proof()
    target = dict(selection=chosen, evidence=external, record=record, os=observed, proof=verified)[location]
    del target[field]
    with pytest.raises(ObservationCorrelationError):
        if location == "proof":
            correlation_digest(chosen, verified)
        else:
            verify_native_birth(chosen, external, native_record=record, os_identity=observed)


@pytest.mark.parametrize("value", [None, [], "selection", 1, True])
def test_selection_and_evidence_require_objects(value):
    with pytest.raises(ObservationCorrelationError):
        normalize_selection(value)
    with pytest.raises(ObservationCorrelationError):
        normalize_evidence(value)


def test_digest_is_stable_across_key_order_and_json_roundtrip():
    chosen, verified = selection(), proof()
    expected = correlation_digest(chosen, verified)
    assert correlation_digest(dict(reversed(list(chosen.items()))), dict(reversed(list(verified.items())))) == expected
    assert correlation_digest(json.loads(json.dumps(chosen)), json.loads(json.dumps(verified))) == expected
    assert expected.startswith("sha256:") and len(expected) == 71


def test_digest_cannot_promote_operator_attestation_to_machine_provenance():
    verified = proof()
    verified["external_binding_provenance"] = "machine_checked_native_birth"
    with pytest.raises(ObservationCorrelationError):
        correlation_digest(selection(), verified)


def test_different_external_binding_attestation_changes_review_digest():
    external = evidence()
    external["binding_hash"] = "sha256:" + "c" * 64
    changed = verify_native_birth(selection(), external, native_record=native_record(), os_identity=identity())
    assert correlation_digest(selection(), changed) != correlation_digest(selection(), proof())


def test_normalized_selection_is_detached_and_preserves_exact_canonical_ids():
    chosen = selection()
    chosen["session_id"] = "Session-Á"
    clean = normalize_selection(chosen)
    assert clean == chosen and clean is not chosen
    current = dict(clean, session_id="session-á")
    assert not fences_match(clean, current)
