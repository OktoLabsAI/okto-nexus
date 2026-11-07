"""Malformed Core records must fail before any selected PID is queried in OS."""

from contextlib import contextmanager
from copy import deepcopy

from nexus_connector_core.models import (
    ProcessBirthEvidence,
    ProcessBirthRecord,
    SessionKey,
)
import pytest

from okto_nexus.bootstrap.observation_correlation_proof import (
    NativeObservationCorrelationProof,
)
from okto_nexus.domain.herdr_observations import HerdrObservationError
import test_observation_correlation_http as http_tests

CREATED, read = http_tests.CREATED, http_tests.read
correlation_http = http_tests.correlation_http


@pytest.mark.parametrize(
    "case", ["boolean_pid", "float_pid", "unsupported_platform", "malformed_birth"]
)
def test_malformed_core_birth_never_opens_an_os_identity(correlation_http, case):
    env = correlation_http
    body = deepcopy(env.body)
    values = dict(
        platform="win32",
        pid=1234,
        birth_token=f"filetime:{CREATED:016x}",
        containment="owned",
    )
    if case == "boolean_pid":
        values["pid"], body["evidence"]["pid"] = True, 1
    elif case == "float_pid":
        values["pid"] = 1234.0
    elif case == "unsupported_platform":
        values["platform"] = "linux"
    else:
        values["birth_token"] = "invalid-native-birth"
    # Frozen dataclasses do not themselves validate these field types/shapes.
    env.birth_record = ProcessBirthRecord(
        SessionKey(
            env.scope["server_id"], env.scope["executor_id"], env.scope["session_id"]
        ),
        "correlation-open",
        ProcessBirthEvidence(**values),
    )
    attempted = []

    @contextmanager
    def forbidden_identity(pid):
        attempted.append(pid)
        raise HerdrObservationError("SYNTHETIC_OS_LOOKUP_NOT_ALLOWED")
        yield  # pragma: no cover - contextmanager protocol without a real handle

    env.app.state.observation_correlation_proof = NativeObservationCorrelationProof(
        env.app.state, identity_guard=forbidden_identity
    )
    response = env.client.post(env.path, headers=env.headers, json=body)
    assert response.status_code in (409, 503), response.text
    assert read(env)["revision"] == 0
    assert attempted == [], "Malformed native evidence reached OS identity acquisition"


@pytest.mark.parametrize("stage", ["core", "os", "audit"])
def test_expired_admission_never_persists_partial_correlation(
    correlation_http, monkeypatch, stage
):
    env = correlation_http
    now = [10.0]
    proof = env.app.state.observation_correlation_proof
    proof.monotonic = lambda: now[0]
    service = env.app.state.observation_correlations

    def expire():
        now[0] = 15.0

    if stage == "core":
        env.during_birth = expire
    elif stage == "os":
        env.during_os = expire
    else:
        emit = service.observations.events.emit

        def emit_then_expire(*args, **kwargs):
            value = emit(*args, **kwargs)
            expire()
            return value

        monkeypatch.setattr(service.observations.events, "emit", emit_then_expire)

    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        before = [
            tuple(row)
            for row in uow.connection.execute(
                "SELECT * FROM observation_rate_buckets ORDER BY scope_kind,scope_id"
            )
        ]
    response = env.client.post(env.path, headers=env.headers, json=env.body)
    assert response.status_code == 503, response.text
    assert read(env)["revision"] == 0
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        assert [
            tuple(row)
            for row in uow.connection.execute(
                "SELECT * FROM observation_rate_buckets ORDER BY scope_kind,scope_id"
            )
        ] == before
        assert (
            uow.connection.execute(
                "SELECT count(*) FROM events WHERE type='observation.correlation'"
            ).fetchone()[0]
            == 0
        )
    assert env.os_calls == env.os_closed == (0 if stage == "core" else 1)
    assert env.active == 0


@pytest.mark.parametrize(
    "changed", ["instance_generation", "operator_disabled", "clear"]
)
def test_authority_changes_during_os_read_are_fenced_at_commit(
    correlation_http, changed
):
    env = correlation_http

    def mutate():
        if changed == "clear":
            context = http_tests.RuntimeRequestContext(
                None, "http_loopback", trusted_local_operator=True
            )
            env.app.state.observation_correlations.clear(
                context=context,
                observed_instance_id=env.instance["observed_instance_id"],
                body={"expected_revision": 0},
            )
        else:
            sql = {
                "instance_generation": "UPDATE observation_instances SET generation=generation+1",
                "operator_disabled": "UPDATE agents SET is_active=0 WHERE agent_id='operator'",
            }[changed]
            with env.deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute(sql)

    env.during_os = mutate
    response = env.client.post(env.path, headers=env.headers, json=env.body)
    assert response.status_code in (401, 403, 409), response.text
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        values = [
            dict(row)
            for row in uow.connection.execute(
                "SELECT revision,state FROM observation_correlations"
            )
        ]
    assert values == (
        [{"revision": 1, "state": "cleared"}] if changed == "clear" else []
    )
    assert env.birth_calls == env.os_calls == env.os_closed == 1 and env.active == 0
