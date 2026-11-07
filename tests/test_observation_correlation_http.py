"""Real HTTP/SQLite correlation boundaries with synthetic Core and OS proofs.

No application lifespan, runtime composition, journal open or process launch.
The fixture seeds canonical relationships, never a personal provider/session.
"""

from contextlib import contextmanager
from copy import deepcopy
import json
import threading
from types import SimpleNamespace as NS

import anyio
from fastapi.testclient import TestClient
from nexus_connector_core import CoreError
from nexus_connector_core.models import (
    ProcessBirthEvidence,
    ProcessBirthRecord,
    SessionKey,
)
import pytest

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.bootstrap.observation_correlation_proof import (
    NativeObservationCorrelationProof,
)
from okto_nexus.domain.runtime_context import RuntimeRequestContext


MANAGEMENT = "/api/v1/observations"
IMAGE = r"C:\Synthetic OBS12\fixture.exe"
CREATED = 133000000000000000


def forbidden(*args, **kwargs):
    pytest.fail(
        "Correlation attempted runtime composition, journal creation or process launch"
    )


def insert(conn, table, **values):
    conn.execute(
        "INSERT INTO "
        + table
        + "("
        + ",".join(values)
        + ") VALUES("
        + ",".join("?" for _ in values)
        + ")",
        tuple(values.values()),
    )


def seed_native(deps):
    """Valid canonical rows only; no runtime/admission/executor is started."""
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        installation = conn.execute("SELECT * FROM execution_installation").fetchone()
        if installation is None:
            server, executor = "correlation-server", "correlation-executor"
            insert(
                conn,
                "execution_installation",
                singleton=1,
                server_id=server,
                embedded_executor_id=executor,
                schema_revision=1,
                created_at=deps.clock.now_iso(),
            )
        else:
            server, executor = (
                installation["server_id"],
                installation["embedded_executor_id"],
            )
        if (
            conn.execute(
                "SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=?",
                (server, executor),
            ).fetchone()
            is None
        ):
            insert(
                conn,
                "execution_executors",
                server_id=server,
                executor_id=executor,
                kind="embedded",
                control_state="CONTROL_READY",
                generation=7,
                owner_instance_id="correlation-owner",
            )
        else:
            conn.execute(
                "UPDATE execution_executors SET control_state='CONTROL_READY',generation=7,owner_instance_id='correlation-owner' WHERE server_id=? AND executor_id=?",
                (server, executor),
            )
        now = deps.clock.now_iso()
        insert(
            conn,
            "runtime_profiles",
            profile_id="correlation-profile",
            adapter_id="fixture",
            config="{}",
            created_at=now,
            updated_at=now,
        )
        insert(
            conn,
            "agent_endpoints",
            endpoint_id="correlation-endpoint",
            agent_id="observed",
            workspace_id="obs-workspace",
            adapter_id="fixture",
            protocol="nxl-r4",
            profile_id="correlation-profile",
            enabled=1,
            activation_state="approved",
            created_at=now,
            updated_at=now,
        )
        insert(
            conn,
            "execution_workspace_bindings",
            server_id=server,
            executor_id=executor,
            workspace_binding_id="correlation-workspace-binding",
            workspace_id="obs-workspace",
            realization_handle="synthetic",
            revision=1,
            status="READY",
        )
        insert(
            conn,
            "execution_realizations",
            server_id=server,
            executor_id=executor,
            realization_ref="correlation-realization",
            local_realization_ref="synthetic-local",
            subject_agent_id="observed",
            workspace_binding_id="correlation-workspace-binding",
            candidate_ref="synthetic-candidate",
            inventory_revision="synthetic-inventory",
            configuration_digest="sha256:" + "a" * 64,
            local_root_proof_digest="sha256:" + "b" * 64,
            revision=1,
            status="READY",
        )
        insert(
            conn,
            "execution_bindings",
            server_id=server,
            executor_id=executor,
            binding_id="correlation-binding",
            endpoint_id="correlation-endpoint",
            workspace_binding_id="correlation-workspace-binding",
            candidate_ref="synthetic-candidate",
            inventory_revision="synthetic-inventory",
            realization_ref="correlation-realization",
            realization_revision=1,
            binding_revision=1,
        )
        scope = dict(
            server_id=server,
            executor_id=executor,
            session_id="correlation-session",
            binding_id="correlation-binding",
            workspace_binding_id="correlation-workspace-binding",
            session_owner_generation=3,
            agent_id="observed",
            workspace_id="obs-workspace",
        )
        insert(
            conn,
            "execution_operations",
            server_id=server,
            executor_id=executor,
            operation_id="correlation-open",
            subject_agent_id="observed",
            actor_agent_id="operator",
            binding_id="correlation-binding",
            workspace_id="obs-workspace",
            workspace_binding_id="correlation-workspace-binding",
            session_id="correlation-session",
            action="runtime.open",
            intent_hash="sha256:" + "c" * 64,
            semantic_payload="{}",
            expected_revisions_json=json.dumps(dict(scope, binding_revision=1)),
            admission_state="RESOLVED_TERMINAL",
            created_at=now,
        )
        insert(
            conn,
            "execution_sessions",
            server_id=server,
            executor_id=executor,
            session_id="correlation-session",
            binding_id="correlation-binding",
            workspace_id="obs-workspace",
            workspace_binding_id="correlation-workspace-binding",
            open_operation_id="correlation-open",
            owner_generation=3,
            lifecycle_state="READY",
            stream_epoch="correlation-stream",
            lease_state="ACTIVE",
        )
    return scope


@pytest.fixture
def correlation_http(tmp_path, monkeypatch, request):
    from okto_nexus.bootstrap import embedded_inventory, runtime_host
    import subprocess

    monkeypatch.setattr(
        embedded_inventory, "discover_local_candidates", lambda **_: NS(candidates=())
    )
    monkeypatch.setattr(runtime_host, "open_journal", forbidden)
    monkeypatch.setattr(runtime_host, "create_runtime", forbidden)
    monkeypatch.setattr(runtime_host.EmbeddedRuntimeHost, "_compose", forbidden)

    class NoProcess:
        def __class_getitem__(cls, _):
            return cls  # Preserve import-time MCP SDK Popen[bytes] annotations.

        def __init__(self, *args, **kwargs):
            forbidden()

    monkeypatch.setattr(subprocess, "Popen", NoProcess)
    deps = bootstrap(
        {},
        [
            "--home",
            str(tmp_path),
            "--feature-observations",
            "true",
            "--feature-harness-integrations",
            "false",
            "--embedding-mode",
            "off",
            "--metrics-mode",
            "disabled",
        ],
    )
    request.addfinalizer(deps.connection_factory.close)
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    _, operator_key = ensure_operator_key(deps, auth)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="observed")
        agent_key = auth.issue_key(uow, agent_id="observed")
        deps.repos.agents.set_permissions(
            uow,
            agent_id="observed",
            preset_id=None,
            permissions={"observations": {"manage_self": True, "publish": True}},
        )
        deps.repos.workspaces.upsert(uow, workspace_id="obs-workspace")
    app = build_app(deps)
    client = TestClient(app, base_url="http://testserver")  # Deliberately no lifespan.
    request.addfinalizer(client.close)
    headers = {"Authorization": "Bearer " + operator_key}

    def post(path, body):
        response = client.post(path, headers=headers, json=body)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    source = post(
        MANAGEMENT + "/sources",
        dict(
            agent_id="observed",
            source_kind="custom",
            workspace_ids=["obs-workspace"],
            registration_ref="synthetic-correlation-source",
        ),
    )["source"]
    source_path = MANAGEMENT + "/sources/" + source["source_id"]
    instance = post(
        source_path + "/instances",
        dict(
            expected_revision=source["revision"],
            workspace_id="obs-workspace",
            external_instance_ref="synthetic-external-instance",
        ),
    )["instance"]
    token = post(
        source_path + "/tokens",
        dict(
            expected_revision=source["revision"],
            instance_grants=[
                dict(
                    observed_instance_id=instance["observed_instance_id"],
                    generation=instance["generation"],
                )
            ],
        ),
    )["token"]
    payload = dict(
        schema_version=1,
        source_id=source["source_id"],
        observed_instance_id=instance["observed_instance_id"],
        generation=instance["generation"],
        sequence=1,
        state="working",
        evidence="inferred",
        observed_at=deps.clock.now_iso(),
    )
    published = client.post(
        "/v1/observations/activity",
        headers={"Authorization": "Bearer " + token},
        json=payload,
    )
    assert published.status_code == 200, published.text
    scope = seed_native(deps)
    selection = {
        key: scope[key]
        for key in (
            "server_id",
            "executor_id",
            "session_id",
            "binding_id",
            "workspace_binding_id",
            "session_owner_generation",
        )
    }
    selection.update(
        source_id=source["source_id"],
        source_revision=source["revision"],
        observed_instance_id=instance["observed_instance_id"],
        generation=instance["generation"],
        open_operation_id="correlation-open",
        stream_epoch="correlation-stream",
        expected_correlation_revision=0,
    )
    evidence = dict(
        kind="local_windows_process_v1",
        host_id="a" * 64,
        pid=1234,
        creation_filetime=CREATED,
        image_path=IMAGE,
        binding_hash="sha256:" + "d" * 64,
    )
    env = NS(
        deps=deps,
        app=app,
        client=client,
        headers=headers,
        agent_key=agent_key,
        publish_token=token,
        source=source,
        instance=instance,
        source_path=source_path,
        scope=scope,
        body={"selection": selection, "evidence": evidence},
        active=0,
        birth_calls=0,
        os_calls=0,
        os_closed=0,
        verified=0,
        during_birth=None,
        during_os=None,
        os_error=None,
        birth_error=None,
        birth_record=None,
    )
    env.path = (
        MANAGEMENT + "/instances/" + instance["observed_instance_id"] + "/correlation"
    )
    env.birth_record = ProcessBirthRecord(
        SessionKey(scope["server_id"], scope["executor_id"], scope["session_id"]),
        "correlation-open",
        ProcessBirthEvidence(
            platform="win32",
            pid=1234,
            birth_token=f"filetime:{CREATED:016x}",
            containment="owned",
        ),
    )
    original_uow = deps.connection_factory.unit_of_work

    @contextmanager
    def tracked_uow(*args, **kwargs):
        with original_uow(*args, **kwargs) as uow:
            env.active += 1
            try:
                yield uow
            finally:
                env.active -= 1

    monkeypatch.setattr(deps.connection_factory, "unit_of_work", tracked_uow)

    async def read_birth(**selected):
        assert env.active == 0, "A SQLite transaction was held across the Core await"
        env.birth_calls += 1
        assert selected == {
            key: scope[key] for key in ("server_id", "executor_id", "session_id")
        }
        await anyio.sleep(0)
        if env.during_birth:
            env.during_birth()
        assert env.active == 0
        if env.birth_error:
            raise env.birth_error
        return env.birth_record

    host = NS(
        _closing=False,
        _history_closing=False,
        read_existing_process_birth=read_birth,
        acquire=forbidden,
        with_history=forbidden,
        _compose=forbidden,
        _open_ledger=forbidden,
    )
    owner = NS(
        host=host,
        _stopping=threading.Event(),
        failure=None,
        state_failure=None,
        recovery_failure=None,
        channel=NS(
            server_id=scope["server_id"],
            executor_id=scope["executor_id"],
            connection_id="correlation-owner",
            connection_generation=7,
        ),
        sessions={scope["session_id"]: {"scope": dict(scope), "executor": object()}},
    )

    def verify(*, uow):
        assert env.active == 1 and uow.connection.in_transaction
        env.verified += 1

    owner.verify = verify
    env.owner, env.host = owner, host
    app.state.embedded_dispatch_owner = owner
    app.state.embedded_core_host = host

    @contextmanager
    def identity_guard(pid):
        assert env.active == 0, (
            "A SQLite transaction was held during an OS identity read"
        )
        assert pid == 1234
        env.os_calls += 1

        def alive():
            assert env.active == 0
            if env.during_os:
                env.during_os()
            if env.os_error:
                raise env.os_error
            return NS(
                host_id="a" * 64, pid=1234, creation_filetime=CREATED, image_path=IMAGE
            )

        try:
            yield NS(require_alive=alive)
        finally:
            assert env.active == 0, (
                "Commit did not close its transaction before the OS guard"
            )
            env.os_closed += 1

    app.state.observation_correlation_proof = NativeObservationCorrelationProof(
        app.state, identity_guard=identity_guard
    )
    yield env


def read(env):
    response = env.client.get(env.path, headers=env.headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["data"]["correlation"]


def canonical_rows(env):
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        tables = [
            row[0]
            for row in uow.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'execution_%' OR name IN ('agent_endpoints','runtime_profiles','sessions','agents'))"
            )
        ]
        return {
            name: sorted(
                (
                    tuple(row)
                    for row in uow.connection.execute('SELECT * FROM "' + name + '"')
                ),
                key=repr,
            )
            for name in tables
        }


def test_exact_http_selection_and_clear_are_historical_metadata_only(correlation_http):
    env = correlation_http
    before = canonical_rows(env)
    assert read(env)["state"] == "absent"
    assert env.birth_calls == env.os_calls == 0
    response = env.client.post(env.path, headers=env.headers, json=env.body)
    assert response.status_code == 200, response.text
    value = response.json()["data"]["correlation"]
    assert value == read(env)
    assert (
        value["revision"] == 1
        and value["state"] == "selected"
        and value["current"] is True
    )
    assert value["selection"] == env.body["selection"]
    assert (
        value["provenance"]["external_binding_provenance"]
        == "operator_attested_external_binding"
    )
    assert (
        value["provenance"]["native_birth_provenance"] == "machine_checked_native_birth"
    )
    assert env.birth_calls == env.os_calls == env.os_closed == 1 and env.verified == 3
    assert (
        IMAGE not in response.text
        and env.publish_token not in response.text
        and "proof" not in value
    )
    assert canonical_rows(env) == before
    retry = env.client.post(env.path, headers=env.headers, json=env.body)
    assert retry.status_code == 409 and env.birth_calls == 1
    cleared = env.client.request(
        "DELETE", env.path, headers=env.headers, json={"expected_revision": 1}
    )
    assert cleared.status_code == 200, cleared.text
    assert read(env)["revision"] == 2 and read(env)["state"] == "cleared"
    assert canonical_rows(env) == before and env.birth_calls == 1
    body = deepcopy(env.body)
    body["selection"]["expected_correlation_revision"] = 2
    reselected = env.client.post(env.path, headers=env.headers, json=body)
    assert reselected.status_code == 200 and read(env)["revision"] == 3


@pytest.mark.parametrize("audience", ["anonymous", "self", "publish"])
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_only_operator_can_read_select_or_clear(correlation_http, audience, method):
    env = correlation_http
    headers = (
        {}
        if audience == "anonymous"
        else {
            "Authorization": "Bearer "
            + (env.agent_key if audience == "self" else env.publish_token)
        }
    )
    body = env.body if method == "POST" else {"expected_revision": 0}
    response = env.client.request(
        method, env.path, headers=headers, **({} if method == "GET" else {"json": body})
    )
    assert response.status_code in (401, 403), response.text
    assert env.birth_calls == env.os_calls == 0 and read(env)["revision"] == 0


@pytest.mark.parametrize("field", ["proof", "native_record", "os_identity"])
def test_client_cannot_supply_native_or_os_proof(correlation_http, field):
    env = correlation_http
    response = env.client.post(
        env.path,
        headers=env.headers,
        json=dict(env.body, **{field: {"private": "DO_NOT_ECHO"}}),
    )
    assert response.status_code == 422 and "DO_NOT_ECHO" not in response.text
    assert env.birth_calls == env.os_calls == 0 and read(env)["revision"] == 0


@pytest.mark.parametrize(
    "changed",
    [
        "source_revision",
        "instance_generation",
        "session_generation",
        "stream_epoch",
        "binding_revision",
        "source_disabled",
        "publisher_revoked",
        "operator_disabled",
        "owner_replaced",
        "session_replaced",
    ],
)
def test_authority_and_exact_fences_are_rechecked_after_core_await(
    correlation_http, changed
):
    env = correlation_http

    def mutate():
        if changed == "owner_replaced":
            env.app.state.embedded_dispatch_owner = NS()
            return
        if changed == "session_replaced":
            env.owner.sessions[env.scope["session_id"]] = dict(
                env.owner.sessions[env.scope["session_id"]]
            )
            return
        sql = {
            "source_revision": "UPDATE observation_sources SET revision=revision+1",
            "instance_generation": "UPDATE observation_instances SET generation=generation+1",
            "session_generation": "UPDATE execution_sessions SET owner_generation=owner_generation+1",
            "stream_epoch": "UPDATE execution_sessions SET stream_epoch='changed-stream'",
            "binding_revision": "UPDATE execution_bindings SET binding_revision=binding_revision+1",
            "source_disabled": "UPDATE observation_sources SET enabled=0",
            "publisher_revoked": "UPDATE observation_tokens SET revoked_at='2026-01-01T00:00:00Z'",
            "operator_disabled": "UPDATE agents SET is_active=0 WHERE agent_id='operator'",
        }[changed]
        with env.deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute(sql)

    env.during_birth = mutate
    response = env.client.post(env.path, headers=env.headers, json=env.body)
    assert response.status_code in (401, 403, 409), response.text
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        assert (
            uow.connection.execute(
                "SELECT count(*) FROM observation_correlations"
            ).fetchone()[0]
            == 0
        )
    assert (
        env.birth_calls == 1 and env.os_calls == env.os_closed == 0 and env.active == 0
    )


def test_clear_during_proof_wins_cas_without_resurrecting_selection(correlation_http):
    env = correlation_http
    context = RuntimeRequestContext(None, "http_loopback", trusted_local_operator=True)
    env.during_birth = lambda: env.app.state.observation_correlations.clear(
        context=context,
        observed_instance_id=env.instance["observed_instance_id"],
        body={"expected_revision": 0},
    )
    response = env.client.post(env.path, headers=env.headers, json=env.body)
    assert response.status_code == 409, response.text
    value = read(env)
    assert (
        value["revision"] == 1
        and value["state"] == "cleared"
        and value["selection"] is None
    )


def test_audit_failure_rolls_back_correlation_and_rate_budget(
    correlation_http, monkeypatch
):
    env = correlation_http
    service = env.app.state.observation_correlations
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        before = [
            tuple(row)
            for row in uow.connection.execute(
                "SELECT * FROM observation_rate_buckets ORDER BY scope_kind,scope_id"
            )
        ]

    def fail(*args, **kwargs):
        raise OSError("DO_NOT_ECHO private storage " + env.publish_token)

    monkeypatch.setattr(service.observations.events, "emit", fail)
    response = env.client.post(env.path, headers=env.headers, json=env.body)
    assert (
        response.status_code == 503
        and "DO_NOT_ECHO" not in response.text
        and env.publish_token not in response.text
    )
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


def test_lost_postcommit_response_is_recovered_by_exact_get(
    correlation_http, monkeypatch
):
    env = correlation_http
    service, failed = env.app.state.observation_correlations, []
    public = service._public

    def fail_once(value, *, current):
        if value is not None and value["state"] == "selected" and not failed:
            failed.append(True)
            raise OSError("DO_NOT_ECHO response lost after commit")
        return public(value, current=current)

    monkeypatch.setattr(service, "_public", fail_once)
    response = env.client.post(env.path, headers=env.headers, json=env.body)
    assert response.status_code == 503 and "DO_NOT_ECHO" not in response.text
    value = read(env)
    assert value["revision"] == 1 and value["selection"] == env.body["selection"]
    retry = env.client.post(env.path, headers=env.headers, json=env.body)
    assert retry.status_code == 409 and read(env) == value and env.birth_calls == 1


@pytest.mark.parametrize(
    "failure", ["core", "os", "core_mismatch", "core_absent", "external_birth"]
)
def test_unavailable_or_mismatched_proof_never_persists_or_leaks(
    correlation_http, failure
):
    env = correlation_http
    body = deepcopy(env.body)
    if failure == "core":
        env.birth_error = CoreError(
            "SESSION_UNKNOWN", "DO_NOT_ECHO synthetic core error"
        )
    elif failure == "os":
        env.os_error = OSError("DO_NOT_ECHO synthetic OS error")
    elif failure == "core_absent":
        env.birth_record = None
    elif failure == "core_mismatch":
        env.birth_record = ProcessBirthRecord(
            SessionKey(env.scope["server_id"], env.scope["executor_id"], "other"),
            "correlation-open",
            ProcessBirthEvidence(
                platform="win32",
                pid=1234,
                birth_token=f"filetime:{CREATED:016x}",
                containment="owned",
            ),
        )
    else:
        body["evidence"]["creation_filetime"] += 1
    response = env.client.post(env.path, headers=env.headers, json=body)
    assert response.status_code in (409, 503), response.text
    assert (
        "DO_NOT_ECHO" not in response.text
        and IMAGE not in response.text
        and read(env)["revision"] == 0
    )
    assert env.os_calls == (1 if failure in {"os", "external_birth"} else 0)
    assert env.os_closed == env.os_calls


def test_feature_off_read_and_clear_do_not_acquire_proof(correlation_http):
    env = correlation_http
    response = env.client.post(env.path, headers=env.headers, json=env.body)
    assert response.status_code == 200, response.text
    env.deps.config.feature_observations = False
    historical = read(env)
    assert historical["revision"] == 1 and historical["current"] is False
    response = env.client.request(
        "DELETE", env.path, headers=env.headers, json={"expected_revision": 1}
    )
    assert response.status_code == 200 and read(env)["state"] == "cleared"
    assert env.birth_calls == env.os_calls == env.os_closed == 1
