"""Actual production inbox/dispatcher/native pipe/journal result correlation."""
import sys
import time

from test_pr34_remediation import runtime as runtime_fixture, send_message
from test_runtime_outbox import operation

runtime = runtime_fixture


def test_terminal_is_correlated_to_transport_attempt_and_releases_lane(runtime):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    deps, client, root, peers, operator_key, _ = runtime
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", _FAKE_SERVER_SOURCE],
        cwd=root, env=kwargs["backend"]["env"])
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator_key},
        json={"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    for _ in range(2):
        created = send_message(runtime, body="fixture result")
        operation_id = created["runtime_operations"][0]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            row = operation(runtime, operation_id)
            if row["status"] == "ACCEPTED" and row.get("terminal_event_id"):
                break
            time.sleep(.02)
        assert row["status"] == "ACCEPTED", "native completion left transport unconfirmed"
        assert row.get("terminal_event_id"), "terminal has no durable attempt correlation"
        with deps.connection_factory.unit_of_work(write=False) as uow:
            result = uow.connection.execute("SELECT operation_id,attempt_id FROM runtime_results WHERE event_id=?",
                (row["terminal_event_id"],)).fetchone()
            assert dict(result) == {"operation_id": operation_id, "attempt_id": row["attempt_id"]}
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_journal_checkpoint SET ordinal=0")
    ingress = deps.harness_supervisor.event_ingress
    for _ in range(20):
        ingress.recover()
        if not ingress.projection_pending:
            break
    assert not ingress.projection_pending
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE operation_id IS NOT NULL").fetchone()[0] == 2


def test_stale_terminal_cannot_free_lane_and_matching_interrupt_wakes_next(runtime):
    from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
    from test_harness_codex_connector import _FAKE_SERVER_SOURCE
    from test_runtime_outbox import wait_status
    deps, client, root, _, operator_key, _ = runtime
    source = _FAKE_SERVER_SOURCE.replace('    if "TRIGGER_HOLD" in text:',
        '    if "TRIGGER_HOLD" in text:\n'
        '        write_msg({"method":"turn/completed", "params":{"threadId":thread_id, "turn":{"id":"stale", "status":"completed"}}})\n'
        '    if "TRIGGER_HOLD" in text:')
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source], cwd=root, env=kwargs["backend"]["env"])
    headers = {"x-api-key": operator_key}
    opened = client.post("/api/v1/harness/sessions", headers=headers,
        json={"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    session_id = opened.json()["data"]["session_id"]
    first = send_message(runtime, body="TRIGGER_HOLD")["runtime_operations"][0]
    wait_status(runtime, first, "ACCEPTED")
    second = send_message(runtime, body="next fixture")["runtime_operations"][0]
    deps.runtime_dispatcher.scan_once()
    assert operation(runtime, second)["status"] == "PENDING"
    assert operation(runtime, first)["terminal_event_id"] is None
    deadline = time.monotonic() + 5
    stale = None
    while time.monotonic() < deadline:
        stale = next((event for event in deps.harness_supervisor.replay_events(session_id)
                      if event.turn_id == "stale"), None)
        if stale:
            break
        time.sleep(.02)
    assert stale is not None and stale.operation_id is None
    interrupted = client.post(f"/api/v1/harness/sessions/{session_id}/interrupt", headers=headers, json={})
    assert interrupted.status_code == 200, interrupted.text
    wait_status(runtime, second, "ACCEPTED")
    assert operation(runtime, first)["terminal_event_id"] is not None
