"""External observations: strict intent, bounded age and isolated token syntax."""
from dataclasses import FrozenInstanceError
import hashlib
import json

import pytest

from okto_nexus.domain.observation_tokens import (
    OBSERVATION_TOKEN_PREFIX,
    generate_observation_token,
    hash_observation_token,
    is_well_formed_observation_token,
)
from okto_nexus.domain.observations import (
    ObservationLimits,
    ObservationReport,
    REASON_CODES,
    compute_freshness,
    parse_report,
    report_hash,
)
from okto_nexus.domain.poll_tokens import is_well_formed_poll_token
from okto_nexus.domain.keys import is_well_formed_api_key
from okto_nexus.errors import OktoNexusError


NOW = "2026-11-06T15:00:00.000000Z"


def payload(**changes):
    return dict(schema_version=1, source_id="src_external", observed_instance_id="obs_external",
                generation=1, sequence=1, state="working", evidence="reported",
                observed_at=NOW, **changes)


def changed(**changes):
    result = payload()
    result.update(changes)
    return result


def rejected(value, *, field=None):
    with pytest.raises(OktoNexusError) as error:
        parse_report(value)
    assert error.value.code == "VALIDATION_ERROR"
    if field is not None:
        assert error.value.details == {"field": field}
    return error.value


def test_parse_returns_immutable_detached_canonical_report_without_authority_fields():
    incoming = payload(reason_code="external_activity", reason_text="Untrusted activity label")
    original = dict(incoming)
    report = parse_report(incoming)
    assert incoming == original
    incoming["state"] = "idle"
    assert report.state == "working"
    assert report.valid_for_seconds == 90
    assert report.observed_at == NOW
    with pytest.raises(FrozenInstanceError):
        report.sequence = 2
    rendered = report.to_dict()
    rendered["state"] = "blocked"
    assert report.state == "working"
    assert not {"agent_id", "workspace_id", "session_id", "received_at", "valid_until"} & report.to_dict().keys()
    assert "Untrusted activity label" not in repr(report)


def test_canonical_hash_normalizes_timezone_default_nulls_and_key_order():
    original = parse_report(payload())
    alternate = changed(observed_at="2026-11-06T12:00:00-03:00", valid_for_seconds=90,
                        reason_code=None, reason_text=None, current_completion_ref=None)
    alternate = parse_report(dict(reversed(list(alternate.items()))))
    assert alternate.to_dict() == original.to_dict()
    digest = report_hash(original)
    assert report_hash(alternate) == digest
    expected = json.dumps(original.to_dict(), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
    assert digest == "sha256:" + hashlib.sha256(expected).hexdigest()
    assert len(digest) == 71


@pytest.mark.parametrize("change", [
    {"source_id": "src_other"}, {"observed_instance_id": "obs_other"},
    {"generation": 2}, {"sequence": 2}, {"state": "blocked"},
    {"evidence": "inferred"}, {"observed_at": "2026-11-06T15:00:00.000001Z"},
    {"valid_for_seconds": 89}, {"reason_code": "external_error"},
    {"reason_text": ""}, {"reason_text": "<script>untrusted</script>"},
    {"current_completion_ref": "opaque:completion/42"},
])
def test_every_semantic_field_changes_replay_hash(change):
    assert report_hash(parse_report(changed(**change))) != report_hash(parse_report(payload()))


@pytest.mark.parametrize("field", ["schema_version", "generation", "sequence", "valid_for_seconds"])
@pytest.mark.parametrize("value", [True, False, 1.0, "1", None, 0, -1])
def test_integer_fields_reject_coercion_and_invalid_values(field, value):
    rejected(changed(**{field: value}), field=field)


@pytest.mark.parametrize("field", ["generation", "sequence"])
def test_sequence_and_generation_are_bounded_signed_64_bit_without_wrap(field):
    assert getattr(parse_report(changed(**{field: (1 << 63) - 1})), field) == (1 << 63) - 1
    rejected(changed(**{field: 1 << 63}), field=field)


@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("valid_for_seconds", 3601),
    ("source_id", ""), ("source_id", " src_bad"), ("source_id", "src/path"),
    ("source_id", "é"), ("source_id", "a" * 161),
    ("observed_instance_id", True), ("observed_instance_id", "obs\n"),
    ("state", "done"), ("state", "completed"), ("state", ["working"]),
    ("evidence", "verified"), ("evidence", {"reported": True}),
    ("reason_code", "arbitrary_safe_code"), ("reason_code", "<img src=x>"),
    ("reason_code", False), ("reason_text", 1), ("reason_text", "a" * 513),
    ("reason_text", "bad\ud800"), ("current_completion_ref", ""),
    ("current_completion_ref", "a" * 257), ("current_completion_ref", "ref\n"),
    ("current_completion_ref", " ref"), ("current_completion_ref", []),
])
def test_closed_strings_and_bounded_fields(field, value):
    rejected(changed(**{field: value}), field=field)


@pytest.mark.parametrize("field", [
    "agent_id", "workspace_id", "session_id", "session_secret", "token",
    "prompt", "frame", "log", "extra", "api_key",
])
def test_identity_and_arbitrary_fields_are_refused_without_echo(field):
    secret = "PRIVATE_BEARER_OR_PROMPT_SHOULD_NOT_APPEAR"
    error = rejected(payload(**{field: secret}), field="fields")
    assert secret not in str(error)
    assert secret not in repr(error.details)
    assert field not in repr(error.details)


@pytest.mark.parametrize("value", [None, [], "{}", True, {1: "value"}])
def test_report_requires_exact_object(value):
    rejected(value, field="fields")


def test_missing_fields_and_mapping_subclasses_do_not_become_reports():
    incomplete = payload()
    incomplete.pop("sequence")
    rejected(incomplete, field="fields")

    class MappingSubclass(dict):
        pass

    rejected(MappingSubclass(payload()), field="fields")
    with pytest.raises(OktoNexusError, match="Invalid observation report"):
        report_hash(payload())


@pytest.mark.parametrize("timestamp", [
    "2026-11-06", "2026-11-06T15:00:00", "2026-11-06 15:00:00Z",
    "2026-11-06T15:00:00.1234567Z", "2026-11-06T15:00:00+00:60",
    "2026-11-06T15:00:00+24:00", "2026-02-30T15:00:00Z",
    "2026-11-06T24:00:00Z", "2026-11-06T15:00:60Z",
    "0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00",
    "2026-W45-5T15:00:00Z", "2026-11-06T15:00:00Z\n", 42,
])
def test_timestamp_requires_valid_explicit_zone_without_lossy_precision(timestamp):
    rejected(changed(observed_at=timestamp), field="observed_at")


def test_boundaries_and_untrusted_text_do_not_invent_completion_or_business_status():
    for state in ("working", "idle", "blocked", "unknown"):
        report = parse_report(changed(state=state, source_id="a" * 160,
                              observed_instance_id="b" * 160, valid_for_seconds=3600,
                              reason_code="external_completion", reason_text="é" * 512))
        assert report.current_completion_ref is None
        assert "current_completion_ref" not in report.to_dict()
    report = parse_report(payload(current_completion_ref="x" * 256,
                                  reason_text="<script>alert(1)</script>\nUntrusted"))
    assert report.current_completion_ref == "x" * 256
    assert report.state == "working"
    assert report.to_dict()["reason_text"].startswith("<script>")
    assert {"external_error", "source_unavailable", "external_input_required"} <= REASON_CODES


@pytest.mark.parametrize("kwargs", [
    {"default_valid_for_seconds": True}, {"max_valid_for_seconds": True},
    {"future_tolerance_seconds": True}, {"default_valid_for_seconds": 0},
    {"max_valid_for_seconds": 0}, {"future_tolerance_seconds": -1},
    {"max_valid_for_seconds": 3601}, {"default_valid_for_seconds": 91, "max_valid_for_seconds": 90},
    {"default_valid_for_seconds": "90"}, {"max_valid_for_seconds": 3600.0},
    {"future_tolerance_seconds": 30.0},
])
def test_limits_are_validated_at_construction(kwargs):
    with pytest.raises(OktoNexusError) as error:
        ObservationLimits(**kwargs)
    assert error.value.code == "VALIDATION_ERROR"


def test_configured_defaults_caps_and_zero_future_tolerance():
    limits = ObservationLimits(default_valid_for_seconds=20, max_valid_for_seconds=30,
                               future_tolerance_seconds=0)
    report = parse_report(payload(), limits=limits)
    assert report.valid_for_seconds == 20
    assert compute_freshness(report, received_at=NOW, limits=limits).valid_until == "2026-11-06T15:00:20.000000Z"
    with pytest.raises(OktoNexusError):
        parse_report(changed(valid_for_seconds=31), limits=limits)
    with pytest.raises(OktoNexusError):
        compute_freshness(parse_report(payload()), received_at=NOW, limits=limits)
    with pytest.raises(OktoNexusError) as error:
        compute_freshness(parse_report(changed(observed_at="2026-11-06T15:00:00.000001Z"),
                                      limits=limits), received_at=NOW, limits=limits)
    assert error.value.details == {"field": "observed_at_future"}
    with pytest.raises(OktoNexusError):
        parse_report(payload(), limits={})


@pytest.mark.parametrize("observed,expected_until", [
    ("2026-11-06T15:00:00Z", "2026-11-06T15:01:30.000000Z"),
    ("2026-11-06T15:00:30Z", "2026-11-06T15:01:30.000000Z"),
    ("2026-11-06T14:59:00Z", "2026-11-06T15:00:30.000000Z"),
    ("2026-11-06T14:58:30.000001Z", "2026-11-06T15:00:00.000001Z"),
])
def test_freshness_is_minimum_of_server_and_observed_lifetimes(observed, expected_until):
    fresh = compute_freshness(parse_report(changed(observed_at=observed)),
                              received_at="2026-11-06T12:00:00-03:00")
    assert fresh.received_at == NOW
    assert fresh.valid_until == expected_until
    with pytest.raises(FrozenInstanceError):
        fresh.valid_until = NOW


@pytest.mark.parametrize("observed,field", [
    ("2026-11-06T15:00:30.000001Z", "observed_at_future"),
    ("2026-11-06T14:58:30Z", "observed_at_expired"),
    ("2026-11-05T15:00:00Z", "observed_at_expired"),
])
def test_future_skew_and_stale_backlog_are_rejected(observed, field):
    with pytest.raises(OktoNexusError) as error:
        compute_freshness(parse_report(changed(observed_at=observed)), received_at=NOW)
    assert error.value.code == "VALIDATION_ERROR"
    assert error.value.details == {"field": field}


def test_expired_duplicate_hash_remains_recognizable_without_renewing_receipt():
    report = parse_report(payload())
    stored_hash = report_hash(report)
    stored_receipt = compute_freshness(report, received_at=NOW)
    duplicate = parse_report(changed(observed_at="2026-11-06T12:00:00-03:00"))
    assert report_hash(duplicate) == stored_hash
    with pytest.raises(OktoNexusError) as error:
        compute_freshness(duplicate, received_at="2026-11-07T15:00:00Z")
    assert error.value.details == {"field": "observed_at_expired"}
    assert stored_receipt.valid_until == "2026-11-06T15:01:30.000000Z"
    assert report_hash(duplicate) == stored_hash


def test_clock_boundaries_and_extreme_policy_do_not_leak_builtin_exceptions():
    with pytest.raises(OktoNexusError) as error:
        compute_freshness(parse_report(changed(observed_at="9999-12-31T23:59:59Z")),
                          received_at="9999-12-31T23:59:59Z")
    assert error.value.details == {"field": "valid_until"}
    with pytest.raises(OktoNexusError):
        compute_freshness(parse_report(payload()), received_at="2026-11-06T15:00:00")
    huge_tolerance = ObservationLimits(future_tolerance_seconds=10 ** 100)
    fresh = compute_freshness(parse_report(changed(observed_at="2027-11-06T15:00:00Z")),
                              received_at=NOW, limits=huge_tolerance)
    assert fresh.valid_until == "2026-11-06T15:01:30.000000Z"


def test_direct_report_construction_still_validates_types_and_normalizes_time():
    with pytest.raises(OktoNexusError):
        ObservationReport(**changed(sequence=True))
    report = ObservationReport(**changed(observed_at="2026-11-06T12:00:00-03:00"))
    assert report.observed_at == NOW


def test_observation_tokens_have_exclusive_family_and_hash_only_representation():
    tokens = [generate_observation_token() for _ in range(4)]
    assert len(set(tokens)) == 4
    for token in tokens:
        assert token.startswith(OBSERVATION_TOKEN_PREFIX)
        assert len(token) == len(OBSERVATION_TOKEN_PREFIX) + 64
        assert is_well_formed_observation_token(token)
        assert not is_well_formed_poll_token(token)
        assert not is_well_formed_api_key(token)
        digest = hash_observation_token(token)
        assert digest == hashlib.sha256(token.encode("ascii")).hexdigest()
        assert len(digest) == 64
        assert token not in digest


@pytest.mark.parametrize("token", [
    None, True, b"nxobs_" + b"a" * 64,
    "nxobs_" + "A" * 64, "nxobs_" + "g" * 64,
    "nxobs_" + "a" * 63, "nxobs_" + "a" * 65,
    "nxobs_" + "a" * 64 + "\n", "nxsept_" + "a" * 64,
    "nxs_" + "a" * 48, "nxc4_" + "a" * 64, "nxt4_" + "a" * 64,
], ids=["none", "bool", "bytes", "uppercase", "invalid_hex", "short", "long",
        "newline", "poll_family", "key_family", "capability_family", "ticket_family"])
def test_token_shape_rejects_other_audiences_and_invalid_forms_without_echo(token):
    assert not is_well_formed_observation_token(token)
    with pytest.raises(OktoNexusError) as error:
        hash_observation_token(token)
    assert error.value.code == "VALIDATION_ERROR"
    assert error.value.message == "Invalid observation token."
    assert error.value.details is None
