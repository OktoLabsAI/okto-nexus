"""Durable administrative command admission through production surfaces."""
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor

from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool

runtime = runtime_fixture


def test_control_admission_does_not_wait_for_native_write(runtime, monkeypatch):
    _, client, _, peers, operator, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    entered, release = threading.Event(), threading.Event()
    send = peers[0].send
    def blocked(session, command):
        if command.verb == "send_turn":
            entered.set()
            assert release.wait(5)
        return send(session, command)
    monkeypatch.setattr(peers[0], "send", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        response = pool.submit(client.post, f"/api/v1/harness/sessions/{sid}/send",
            headers={"x-api-key": operator}, json={"payload": {"text": "fixture"}, "idempotency_key": "blocked-command"})
        try:
            assert entered.wait(2)
            admitted = response.result(timeout=.5)
            assert admitted.status_code == 200, admitted.text
            assert admitted.json()["data"]["durable"] is True
            assert admitted.json()["data"]["external_acceptance"] == "not_observed"
        finally:
            release.set()


def test_repeating_command_key_does_not_repeat_native_effect(runtime):
    deps, client, _, peers, operator, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    body = {"payload": {"text": "fixture"}, "idempotency_key": "same-command"}
    operations = []
    for _ in range(2):
        response = client.post(f"/api/v1/harness/sessions/{sid}/send", headers={"x-api-key": operator}, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["idempotency_key"] == body["idempotency_key"]
        operations.append(response.json()["data"]["operation_id"])
    assert operations[0] == operations[1]
    deadline = time.monotonic() + 3
    while not peers[0].sent and time.monotonic() < deadline:
        time.sleep(.01)
    assert len(peers[0].sent) == 1, "a retried administrative command executed twice"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == 1


def wait_operation(runtime, operation_id, predicate):
    _, client, _, _, operator, _ = runtime
    return wait_command(client, operator, operation_id, predicate)


def wait_command(client, operator, operation_id, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/harness/operations/{operation_id}", headers={"x-api-key": operator})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        if predicate(data):
            return data
        time.sleep(.01)
    assert predicate(data), data


def wait_close_result(client, operator, response):
    data = response.json()["data"] if hasattr(response, "json") else response["data"]
    operation = wait_command(client, operator, data["operation_id"],
        lambda row: row["state"] in {"DONE", "OUTCOME_UNKNOWN", "REJECTED"})
    assert operation["result"], operation
    return operation["result"]


def codex_session(runtime, *, outcome="completed"):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, _, operator, _ = runtime
    source = _FAKE_SERVER_SOURCE.replace('"status": "completed"', '"status": "' + outcome + '"')
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source.replace('"result": {}',
            '\"result\": {\"userAgent\": \"okto-nexus/0.156.1 fixture\"}', 1)], cwd=root, env=kwargs["backend"]["env"])
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator},
        json={"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert response.status_code == 200, response.text
    return response.json()["data"]["session_id"]


def test_two_admin_turns_capture_results_and_close_is_durable(runtime):
    deps, client, _, _, operator, caller = runtime
    sid = codex_session(runtime)
    for index in range(2):
        admitted = tool(client, operator, "harness_send", {"session_id": sid,
            "payload": {"text": f"fixture reply {index}"}, "idempotency_key": f"turn-{index}"})
        assert admitted["ok"], admitted
        op = admitted["data"]["operation_id"]
        result = wait_operation(runtime, op, lambda row: row["result_durable"])
        assert f"fixture reply {index}" in result["result"]["output_text"]
        assert result["external_acceptance"] == "harness_accepted"
        assert not tool(client, caller, "harness_get", {"operation_id": op})["ok"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE command_operation_id IS NOT NULL").fetchone()[0] == 2
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 0
    closed = tool(client, operator, "harness_close", {"session_id": sid})
    assert closed["ok"], closed
    result = wait_operation(runtime, closed["data"]["operation_id"], lambda row: row["state"] == "DONE")
    assert result["result"]["lifecycle_state"] == "stopped"
    repeated = tool(client, operator, "harness_close", {"session_id": sid})
    assert repeated["data"]["operation_id"] == closed["data"]["operation_id"]


def test_interrupt_is_not_queued_behind_a_blocked_normal_write(runtime, monkeypatch):
    _, client, _, peers, operator, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    entered, release = threading.Event(), threading.Event()
    original = peers[0].send
    def blocked(session, command):
        if command.verb == "send_turn":
            entered.set()
            assert release.wait(5)
        return original(session, command)
    monkeypatch.setattr(peers[0], "send", blocked)
    try:
        normal = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "fixture"}})
        assert normal["ok"] and entered.wait(2)
        interrupt = tool(client, operator, "harness_interrupt", {"session_id": sid,
            "expected_operation_id": normal["data"]["operation_id"]})
        assert interrupt["ok"], interrupt
        result = wait_operation(runtime, interrupt["data"]["operation_id"], lambda row: row["state"] == "SENT_UNCONFIRMED")
        assert result["expected_operation_id"] == normal["data"]["operation_id"]
        assert [c.verb for c in peers[0].sent] == ["interrupt"]
    finally:
        release.set()


def test_stale_native_turn_control_is_rejected_without_effect(runtime):
    _, client, _, _, operator, _ = runtime
    sid = codex_session(runtime)
    normal = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "TRIGGER_HOLD"}})
    op = normal["data"]["operation_id"]
    active = wait_operation(runtime, op, lambda row: row["external_acceptance"] == "harness_accepted")
    stale = tool(client, operator, "harness_steer", {"session_id": sid, "payload": {"text": "never"},
        "expected_operation_id": op, "expected_turn_id": "stale-turn"})
    assert not stale["ok"] and stale["error"]["code"] == "CONFLICT"
    interrupt = tool(client, operator, "harness_interrupt", {"session_id": sid,
        "expected_operation_id": op, "expected_turn_id": active["native_turn_id"]})
    assert interrupt["ok"], interrupt
    result = wait_operation(runtime, op, lambda row: row["result_durable"])
    assert result["native_turn_id"] == active["native_turn_id"]


def test_revocation_after_admission_prevents_native_write(runtime, monkeypatch):
    from test_runtime_grants import issue
    deps, client, _, peers, operator, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    grant = issue(runtime, ["send"], max_executions=1)
    runner = deps.runtime_dispatcher.command_dispatcher
    scan = runner.scan_once
    monkeypatch.setattr(runner, "scan_once", lambda: None)
    admitted = tool(client, caller, "harness_send", {"session_id": sid, "payload": {"text": "never"}})
    assert admitted["ok"], admitted
    assert client.delete(f"/api/v1/harness/grants/{grant['grant_id']}", headers={"x-api-key": operator}).status_code == 200
    monkeypatch.setattr(runner, "scan_once", scan)
    deps.runtime_dispatcher.wake()
    wait_operation(runtime, admitted["data"]["operation_id"], lambda row: row["state"] == "REJECTED")
    assert peers[0].sent == []


def test_control_queued_for_finished_turn_does_not_hit_next_turn(runtime, monkeypatch):
    deps, client, _, peers, operator, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    peers[0].delivery_event_phase = lambda event: {"fixture/start": "started", "fixture/end": "terminal"}.get(event.native_event)
    normal = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "fixture"}})
    op = normal["data"]["operation_id"]
    wait_operation(runtime, op, lambda row: row["state"] == "SENT_UNCONFIRMED")
    peers[0].push_event(kind="turn_started", native_event="fixture/start")
    wait_operation(runtime, op, lambda row: row["state"] == "ACCEPTED")
    runner = deps.runtime_dispatcher.command_dispatcher
    scan = runner.scan_once
    monkeypatch.setattr(runner, "scan_once", lambda: None)
    control = tool(client, operator, "harness_steer", {"session_id": sid, "payload": {"text": "stale instruction"}, "expected_operation_id": op})
    assert control["ok"], control
    peers[0].push_event(kind="turn_completed", native_event="fixture/end")
    wait_operation(runtime, op, lambda row: row["result_durable"])
    monkeypatch.setattr(runner, "scan_once", scan)
    deps.runtime_dispatcher.wake()
    wait_operation(runtime, control["data"]["operation_id"], lambda row: row["state"] == "REJECTED")
    assert [c.verb for c in peers[0].sent] == ["send_turn"]


def test_claude_replacement_steer_has_separate_correlated_result(runtime):
    from okto_nexus.adapters.outbound.harness.claude_code_stream import ClaudeCodeStreamConnector
    from test_harness_claude_code_connector import _FAKE_CLAUDE_SCRIPT
    deps, client, root, _, operator, _ = runtime
    deps.harness_connector_factories["claude_code"] = lambda **kwargs: ClaudeCodeStreamConnector(
        binary=sys._base_executable, argv=["-u", "-c", _FAKE_CLAUDE_SCRIPT], cwd=root,
        version_argv=["-c", "print('2.1.281 (Claude Code)')"],
        env=kwargs["backend"]["env"] | {"FAKE_CC_SCENARIO": "slow_start"})
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "claude_code", "substrate": "stream", "endpoint_id": "endpoint-claude_code.stream", "project_root": root})
    assert response.status_code == 200, response.text
    sid = response.json()["data"]["session_id"]
    first = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "first"}})
    assert first["ok"], first
    op = first["data"]["operation_id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if any(e.native_event == "stream_event:content_block_start" for e in deps.harness_supervisor.replay_events(sid)):
            break
        time.sleep(.005)
    steered = tool(client, operator, "harness_steer", {"session_id": sid, "payload": {"text": "steered"}, "expected_operation_id": op})
    assert steered["ok"], steered
    first_result = wait_operation(runtime, op, lambda row: row["result_durable"])
    second_result = wait_operation(runtime, steered["data"]["operation_id"], lambda row: row["result_durable"])
    assert "echo:steered" in second_result["result"]["output_text"]
    assert first_result["result"]["result_id"] != second_result["result"]["result_id"]


def test_idempotent_retry_does_not_charge_spent_grant_again(runtime):
    from test_runtime_grants import issue
    deps, client, _, _, _, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    grant = issue(runtime, ["send"], max_executions=1)
    args = {"session_id": sid, "payload": {"text": "fixture"}, "idempotency_key": "one-grant-charge"}
    first = tool(client, caller, "harness_send", args)
    repeated = tool(client, caller, "harness_send", args)
    assert first["ok"] and repeated["ok"], (first, repeated)
    assert first["data"]["operation_id"] == repeated["data"]["operation_id"]
    different = tool(client, caller, "harness_send", args | {"payload": {"text": "changed"}})
    assert not different["ok"] and different["error"]["code"] == "CONFLICT"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == 1


def test_enqueue_failure_rolls_back_intent_and_grant_charge(runtime, monkeypatch):
    from test_runtime_grants import issue
    deps, client, _, peers, _, caller = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    grant = issue(runtime, ["send"], max_executions=1)
    repo = deps.runtime_dispatcher.command_dispatcher.repo
    enqueue = repo.enqueue
    def fail(*args, **kwargs):
        enqueue(*args, **kwargs)
        raise OSError("fixture rollback before commit")
    monkeypatch.setattr(repo, "enqueue", fail)
    result = tool(client, caller, "harness_send", {"session_id": sid, "payload": {"text": "never"}})
    assert not result["ok"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?", (grant["grant_id"],)).fetchone()[0] == 0
        assert uow.connection.execute("SELECT count(*) FROM runtime_commands").fetchone()[0] == 0
    assert not peers[0].sent


def test_command_result_recovers_after_owner_restart_without_reexecution(runtime, monkeypatch):
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_dispatcher
    from okto_nexus.application.runtime_shutdown import shutdown_runtime
    deps, client, _, _, operator, _ = runtime
    sid = codex_session(runtime)
    ingress = deps.harness_supervisor.event_ingress
    project = ingress.repo.project
    def fail_terminal(uow, **kwargs):
        if kwargs["event"].delivery_phase == "terminal":
            raise OSError("fixture projection cut after journal fsync")
        return project(uow, **kwargs)
    monkeypatch.setattr(ingress.repo, "project", fail_terminal)
    admitted = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": "captured admin result"}})
    op = admitted["data"]["operation_id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if ingress.projection_pending and any(r["event"].get("operation_id") == op and r["event"].get("delivery_phase") == "terminal" for r in ingress.journal.read_after(0)):
            break
        time.sleep(.01)
    assert ingress.projection_pending
    deps.harness_supervisor.close(sid)
    old = deps.runtime_dispatcher
    old.close()
    ingress.close()
    old._shutdown_finished.set()
    recovered = bootstrap({}, ["--home", str(deps.config.home_dir)])
    recovered.config.feature_harness_integrations = True
    launches = []
    def forbidden(**kwargs):
        launches.append(kwargs)
        raise AssertionError("recovery replayed the command")
    recovered.harness_connector_factories = {kind: forbidden for kind in ("pi", "codex", "claude_code")}
    new = build_dispatcher(recovered)
    assert new.start()
    try:
        with recovered.connection_factory.unit_of_work(write=False) as uow:
            command = new.command_dispatcher.repo.get(uow, op)
            assert command["terminal_event_id"] and command["status"] == "ACCEPTED"
            result = uow.connection.execute("SELECT * FROM runtime_results WHERE command_operation_id=?", (op,)).fetchone()
            assert "captured admin result" in result["output_text"]
        assert not launches
    finally:
        shutdown_runtime(new, recovered.harness_supervisor)
