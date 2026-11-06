"""Attention invalidations over real TCP, with isolated SQLite and no harness."""

from contextlib import contextmanager
import json
import math
import socket
import sqlite3
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
import uvicorn

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
from okto_nexus.adapters.inbound.http.attention_stream import _gap
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.bootstrap import dependencies, embedded_inventory
from test_attention_api import ACCOUNT, Clock, parked, snapshot


PATH = "/api/v1/stream?view=attention"


@pytest.fixture
def stream_env(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(dependencies, "SystemClock", lambda: clock)
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=()))
    deps = dependencies.bootstrap({}, ["--home", str(tmp_path / "home"),
        "--feature-harness-integrations", "false", "--embedding-mode", "off"])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    _, key = ensure_operator_key(deps, auth)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id="attention-one", display_name="Attention fixture")
        deps.repos.agents.upsert(uow, agent_id="attention-worker")
        worker_key = auth.issue_key(uow, agent_id="attention-worker")
    app = build_app(deps)
    app.state.sse_poll_seconds = 0.05
    app.state.sse_ping_seconds = 0.1
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    app.state.server = server
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "uvicorn did not start"
            time.sleep(0.02)
        yield SimpleNamespace(deps=deps, app=app, clock=clock, server=server, thread=thread,
                              base=f"http://127.0.0.1:{port}", key=key, worker_key=worker_key)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "attention SSE prevented server shutdown"


def client(env, **kwargs):
    return httpx.Client(base_url=env.base, timeout=5, trust_env=False, **kwargs)


def frames(response):
    current = {}
    for line in response.iter_lines():
        if not line:
            if current:
                yield current
                current = {}
        elif line.startswith("id: "):
            current["id"] = int(line[4:])
        elif line.startswith("event: "):
            current["event"] = line[7:]
        elif line.startswith("data: "):
            current["data"] = json.loads(line[6:])
        elif line.startswith(":"):
            current["comment"] = line[1:].strip()


def next_event(iterator):
    deadline = time.monotonic() + 5
    for frame in iterator:
        assert time.monotonic() < deadline, "attention event did not arrive"
        if "event" in frame:
            return frame
    raise AssertionError("attention stream ended before its control event")


def ended(iterator):
    deadline = time.monotonic() + 5
    for frame in iterator:
        assert time.monotonic() < deadline, "attention stream did not close"
        assert "event" not in frame, frame


def control(frame, event, reason, *, clear=False):
    assert frame["event"] == event
    assert set(frame) == {"id", "event", "data"}
    assert set(frame["data"]) == {"version", "event_cursor", "reason", "clear"}
    assert frame["data"] == dict(version=1, event_cursor=frame["id"], reason=reason, clear=clear)


def emit(env, count=1, *, prune=None):
    """Commit an entire event burst and optional retention in one transaction."""
    with env.deps.connection_factory.unit_of_work() as uow:
        for index in range(count):
            last = env.deps.event_emitter.emit(uow, workspace_id="attention-one", stream="workspace",
                type="execution.output", actor_agent_id="attention-worker", visibility="public",
                payload={"text": "historical-private-output-marker", "index": index})
        if prune == "all":
            uow.connection.execute("DELETE FROM events")
        elif prune == "keep-last":
            uow.connection.execute("DELETE FROM events WHERE event_id < ?", (last,))
    return last


def latest(env):
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        return uow.connection.execute("SELECT COALESCE((SELECT seq FROM sqlite_sequence WHERE name='events'),0)").fetchone()[0]


def opened(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    return frames(response)


def fail_bounds(env, monkeypatch):
    """Inject a SQLite read fault at bounds SQL; keep real UoWs and HTTP."""
    original = env.deps.connection_factory.unit_of_work

    class Connection:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def execute(self, sql, *args, **kwargs):
            if "SELECT COALESCE((SELECT seq FROM sqlite_sequence WHERE name='events')" in sql:
                raise sqlite3.OperationalError("private-database-path-and-token-marker")
            return self.wrapped.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    class UnitOfWork:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.connection = Connection(wrapped.connection)

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    @contextmanager
    def guarded(*args, **kwargs):
        with original(*args, **kwargs) as uow:
            yield UnitOfWork(uow)

    monkeypatch.setattr(env.deps.connection_factory, "unit_of_work", guarded)


def test_initial_and_reconnect_reset_never_replay_historical_payload(stream_env):
    env = stream_env
    last = emit(env, 3)
    with client(env) as http:
        for headers, suffix in (({}, ""), ({"Last-Event-ID": str(last - 1)}, ""),
                                ({}, "&last_event_id=" + str(last))):
            with http.stream("GET", PATH + suffix, headers={"x-api-key": env.key, **headers}) as response:
                iterator = opened(response)
                first = next_event(iterator)
                control(first, "attention-reset", "snapshot_required")
                assert first["id"] == last
                assert "historical-private-output-marker" not in json.dumps(first)


def test_canonical_occurrence_and_large_burst_emit_metadata_batches(stream_env):
    env = stream_env
    with client(env) as http, http.stream("GET", PATH, headers={"x-api-key": env.key}) as response:
        iterator = opened(response)
        control(next_event(iterator), "attention-reset", "snapshot_required")
        parked(env)
        parked_cursor = latest(env)
        while True:
            event = next_event(iterator)
            control(event, "attention-invalidated", "canonical_change")
            if event["id"] >= parked_cursor:
                break
        view = http.get("/api/v1/attention?kind=delivery_parked", headers={"x-api-key": env.key})
        assert view.status_code == 200 and view.json()["data"]["total"] == 1
        last = emit(env, 1001)
        batches = []
        while True:
            event = next_event(iterator)
            control(event, "attention-invalidated", "canonical_change")
            batches.append(event)
            if event["id"] == last:
                break
        assert len(batches) == math.ceil(1001 / 500)
        assert [event["id"] for event in batches] == sorted({event["id"] for event in batches})
        assert "historical-private-output-marker" not in json.dumps(batches)


@pytest.mark.parametrize("prune", ["all", "keep-last"])
def test_atomic_insert_and_retention_between_polls_resets_even_from_zero(stream_env, prune):
    env = stream_env
    assert latest(env) == 0
    with client(env) as http, http.stream("GET", PATH, headers={"x-api-key": env.key}) as response:
        iterator = opened(response)
        first = next_event(iterator)
        control(first, "attention-reset", "snapshot_required")
        assert first["id"] == 0
        last = emit(env, 2, prune=prune)
        reset = next_event(iterator)
        control(reset, "attention-reset", "retention_gap")
        assert reset["id"] == last
    with client(env) as http, http.stream("GET", PATH, headers={"x-api-key": env.key, "Last-Event-ID": "0"}) as response:
        reset = next_event(opened(response))
        control(reset, "attention-reset", "retention_gap")
        assert reset["id"] == last


@pytest.mark.parametrize("warm", [False, True])
def test_external_key_rotation_clears_open_stream_with_cold_or_warm_auth(stream_env, warm):
    env = stream_env
    with client(env) as http:
        if warm:
            assert http.get("/api/v1/attention", headers={"x-api-key": env.key}).status_code == 200
        with http.stream("GET", PATH, headers={"x-api-key": env.key}) as response:
            iterator = opened(response)
            control(next_event(iterator), "attention-reset", "snapshot_required")
            independent = AgentKeyAuthService(env.deps.repos.agents, env.deps.clock)
            with env.deps.connection_factory.unit_of_work() as uow:
                replacement = independent.issue_key(uow, agent_id="operator")
            control(next_event(iterator), "attention-reset", "authorization_lost", clear=True)
            ended(iterator)
        with http.stream("GET", PATH, headers={"x-api-key": replacement}) as response:
            control(next_event(opened(response)), "attention-reset", "snapshot_required")


def test_cookie_logout_clears_open_stream_and_does_not_fall_back_to_loopback(stream_env):
    env = stream_env
    env.app.state.operator_auth.configure(**ACCOUNT, local=True)
    headers = {"x-nexus-ui": "1", "Origin": env.base}
    with client(env) as http:
        assert http.post("/api/v1/operator-auth/login", json=ACCOUNT, headers=headers).status_code == 200
        with http.stream("GET", PATH, headers={"X-Nexus-Operator-Session-Required": "1"}) as response:
            iterator = opened(response)
            control(next_event(iterator), "attention-reset", "snapshot_required")
            assert http.post("/api/v1/operator-auth/logout", headers=headers).status_code == 200
            control(next_event(iterator), "attention-reset", "authorization_lost", clear=True)
            ended(iterator)
        with http.stream("GET", PATH, headers={"X-Nexus-Operator-Session-Required": "1"}) as response:
            assert response.status_code == 401


def test_disabling_attention_clears_stream_and_refuses_new_stream(stream_env):
    env = stream_env
    with client(env) as http:
        with http.stream("GET", PATH, headers={"x-api-key": env.key}) as response:
            iterator = opened(response)
            control(next_event(iterator), "attention-reset", "snapshot_required")
            assert http.patch("/api/v1/settings", json={"feature_attention": False},
                              headers={"x-api-key": env.key}).status_code == 200
            control(next_event(iterator), "attention-reset", "feature_disabled", clear=True)
            ended(iterator)
        with http.stream("GET", PATH, headers={"x-api-key": env.key}) as response:
            assert response.status_code == 409
            assert response.headers["cache-control"] == "no-store"
            response.read()
            assert response.json()["error"]["code"] == "FEATURE_DISABLED"


def test_ordinary_agent_is_refused_before_streaming(stream_env):
    env = stream_env
    with client(env) as http, http.stream("GET", PATH, headers={"x-api-key": env.worker_key}) as response:
        assert response.status_code == 403
        assert response.headers["cache-control"] == "no-store"
        response.read()
        assert response.json()["ok"] is False
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_idle_stream_is_read_only_after_existing_authentication(stream_env):
    env = stream_env
    with client(env) as http, http.stream("GET", PATH, headers={"x-api-key": env.key}) as response:
        iterator = opened(response)
        control(next_event(iterator), "attention-reset", "snapshot_required")
        # Initial key resolution may retain its pre-existing authentication audit.
        before = snapshot(env)
        pings = 0
        deadline = time.monotonic() + 5
        for frame in iterator:
            assert time.monotonic() < deadline
            assert "event" not in frame
            pings += frame.get("comment") == "ping"
            if pings == 2:
                break
        assert pings == 2
        assert snapshot(env) == before


def test_shutdown_drains_an_open_attention_stream_without_timeout_backstop(stream_env):
    env = stream_env
    assert env.server.config.timeout_graceful_shutdown is None
    with client(env) as http, http.stream("GET", PATH, headers={"x-api-key": env.key}) as response:
        iterator = opened(response)
        control(next_event(iterator), "attention-reset", "snapshot_required")
        env.server.should_exit = True
        env.thread.join(timeout=5)
        assert not env.thread.is_alive(), "open attention stream blocked graceful shutdown"
        ended(iterator)


def test_initial_sqlite_bounds_fault_returns_safe_json_before_stream_headers(stream_env, monkeypatch):
    env = stream_env
    before = snapshot(env)
    fail_bounds(env, monkeypatch)
    # Loopback operator trust isolates the stream read from legacy key touches.
    with client(env) as http, http.stream("GET", PATH) as response:
        assert response.status_code == 503
        assert response.headers["content-type"].startswith("application/json")
        assert response.headers["cache-control"] == "no-store"
        response.read()
        assert response.json()["ok"] is False
        assert response.json()["error"]["code"] == "DB_ERROR"
        assert "unavailable" in response.json()["error"]["message"]
        assert "private-database-path-and-token-marker" not in response.text
    assert snapshot(env) == before


def test_sqlite_bounds_fault_during_stream_requests_resnapshot_without_clear(stream_env, monkeypatch):
    env = stream_env
    with client(env) as http, http.stream("GET", PATH) as response:
        iterator = opened(response)
        initial = next_event(iterator)
        control(initial, "attention-reset", "snapshot_required")
        before = snapshot(env)
        fail_bounds(env, monkeypatch)
        reset = next_event(iterator)
        control(reset, "attention-reset", "source_unavailable", clear=False)
        assert reset["id"] == initial["id"]
        assert "private-database-path-and-token-marker" not in json.dumps(reset)
        ended(iterator)
        assert snapshot(env) == before


def test_sqlite_cookie_revalidation_fault_preserves_authorized_snapshot(stream_env, monkeypatch):
    env = stream_env
    env.app.state.operator_auth.configure(**ACCOUNT, local=True)
    headers = {"x-nexus-ui": "1", "Origin": env.base}
    with client(env) as http:
        assert http.post("/api/v1/operator-auth/login", json=ACCOUNT, headers=headers).status_code == 200
        with http.stream("GET", PATH, headers={"X-Nexus-Operator-Session-Required": "1"}) as response:
            iterator = opened(response)
            initial = next_event(iterator)
            control(initial, "attention-reset", "snapshot_required")
            before = snapshot(env)

            def unavailable(_cookie):
                raise sqlite3.OperationalError("private-cookie-database-marker")

            # Targeted fault in the existing cookie read, after real login.
            monkeypatch.setattr(env.app.state.operator_auth, "resolve", unavailable)
            reset = next_event(iterator)
            control(reset, "attention-reset", "source_unavailable", clear=False)
            assert reset["id"] == initial["id"]
            assert "private-cookie-database-marker" not in json.dumps(reset)
            ended(iterator)
            assert snapshot(env) == before


@pytest.mark.parametrize("after,latest_id,earliest,expected", [
    (0, 0, None, False), (0, 2, None, True), (0, 1, 1, False),
    (0, 2, 2, True), (5, 3, 1, True), (5, 5, None, False),
])
def test_retention_boundary_includes_zero_cursor_and_empty_retained_log(after, latest_id, earliest, expected):
    assert _gap(after, latest_id, earliest) is expected
