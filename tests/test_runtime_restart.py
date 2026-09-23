"""Recovery uses the production composition and real native fixture pipes."""
import sys
import time

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.harness import build_dispatcher
from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from okto_nexus.application.runtime_shutdown import shutdown_runtime
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture, send_message, open_rest
from test_runtime_outbox import operation, wait_status

runtime = runtime_fixture


@pytest.mark.parametrize("blocked_phase", ["started", "terminal"])
@pytest.mark.parametrize("multiple_batches", [False, True])
def test_restart_recovers_captured_old_attempt_without_reexecuting(runtime, monkeypatch, blocked_phase, multiple_batches):
    deps, client, root, _, operator_key, _ = runtime
    source = _FAKE_SERVER_SOURCE
    if multiple_batches:
        line = '    write_msg({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "itemId": item_id, "delta": text}})'
        source = source.replace(line, "    for _ in range(40):\n    " + line)
        assert source != _FAKE_SERVER_SOURCE
    deps.harness_connector_factories["codex"] = lambda **kwargs: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source],
        cwd=root, env=kwargs["backend"]["env"])
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator_key},
        json={"agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert response.status_code == 200
    session_id = response.json()["data"]["session_id"]
    supervisor, old = deps.harness_supervisor, deps.runtime_dispatcher
    ingress = supervisor.event_ingress
    project = ingress.repo.project

    def unavailable_at_cut(uow, **kwargs):
        if kwargs["event"].delivery_phase == blocked_phase:
            raise OSError("fixture database unavailable at durable event cut")
        return project(uow, **kwargs)

    monkeypatch.setattr(ingress.repo, "project", unavailable_at_cut)
    operation_id = send_message(runtime, body="one durable fixture answer")["runtime_operations"][0]
    deadline = time.monotonic() + 5
    captured = False
    while time.monotonic() < deadline:
        captured = any(r["event"].get("delivery_phase") == "terminal"
                       for r in ingress.journal.read_after(max(0, ingress.journal.watermark - 16)))
        if captured:
            break
        time.sleep(.01)
    assert captured and operation(runtime, operation_id)["terminal_event_id"] is None
    # Stop the disposable native peer, but keep the deliberately unprojectable
    # captured tail. Releasing/reopening the actual journal emulates the recovery
    # boundary, without leaving an old process or reusing a provider session.
    supervisor.close(session_id)
    old.close()
    ingress.close()
    old._shutdown_finished.set()
    recovered = bootstrap({}, ["--home", str(deps.config.home_dir)])
    recovered.config.feature_harness_integrations = True
    launches = []

    def forbidden_launch(**kwargs):
        launches.append(kwargs)
        raise AssertionError("recovery must never replay the prompt")

    recovered.harness_connector_factories = {kind: forbidden_launch for kind in ("pi", "codex", "claude_code")}
    dispatcher = build_dispatcher(recovered)
    assert dispatcher.start()
    try:
        with recovered.connection_factory.unit_of_work(write=False) as uow:
            row = dispatcher.repo.get(uow, operation_id)
            assert row["terminal_event_id"], "captured terminal lost correlation across owner takeover"
            assert row["status"] == "ACCEPTED"
            result = uow.connection.execute("SELECT * FROM runtime_results WHERE operation_id=?", (operation_id,)).fetchone()
            assert result and "one durable fixture answer" in result["output_text"]
            assert uow.connection.execute("SELECT status FROM message_deliveries WHERE delivery_id=?",
                (row["delivery_id"],)).fetchone()[0] == "read"
            assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject LIKE 'runtime processing receipt:%'").fetchone()[0] == 1
        assert not launches
    finally:
        shutdown_runtime(dispatcher, recovered.harness_supervisor)


def test_old_attempt_terminal_after_frozen_recovery_boundary_stays_unknown(runtime, monkeypatch):
    from okto_nexus.domain.harness import HarnessEvent
    deps = runtime[0]
    assert open_rest(runtime).status_code == 200
    operation_id = send_message(runtime)["runtime_operations"][0]
    row = wait_status(runtime, operation_id, "SENT_UNCONFIRMED")
    supervisor, old = deps.harness_supervisor, deps.runtime_dispatcher
    session = supervisor.get(row["runtime_session_id"])
    fields = dict(session_id=session.session_id, harness_kind=session.harness_kind,
        origin="native", operation_id=operation_id, attempt_id=row["attempt_id"],
        owner_epoch=old.epoch, thread_id="fixture-thread", turn_id="fixture-turn",
        occurred_at=deps.clock.now_iso())
    supervisor.event_ingress.capture(HarnessEvent(**fields, kind="tool_activity",
        native_event="fixture/started", delivery_phase="started", payload={}), connection_id=session.connection_id)
    assert operation(runtime, operation_id)["status"] == "ACCEPTED"
    # Model an abrupt exit's absent lifecycle records, while explicitly closing
    # the fixture peer for test hygiene. This does not claim a real SIGKILL test.
    monkeypatch.setattr(supervisor, "_capture_lifecycle", lambda *args, **kwargs: None)
    supervisor.close(session.session_id)
    old.close()
    supervisor.event_ingress.close()
    old._shutdown_finished.set()
    recovered = bootstrap({}, ["--home", str(deps.config.home_dir)])
    recovered.config.feature_harness_integrations = True
    dispatcher = build_dispatcher(recovered)
    assert dispatcher.start()
    try:
        ingress = recovered.harness_supervisor.event_ingress
        with recovered.connection_factory.unit_of_work() as uow:
            assert dispatcher.repo.get(uow, operation_id)["status"] == "OUTCOME_UNKNOWN"
            assert not dispatcher.repo.set_recovery_boundary(uow, owner_id=dispatcher.owner_id,
                epoch=dispatcher.epoch, store_id=ingress.journal.store_id,
                watermark=ingress.journal.watermark + 100, now=recovered.clock.now_iso())
        ingress.capture(HarnessEvent(**fields, kind="turn_completed", native_event="fixture/completed",
            delivery_phase="terminal", payload={}, output_text="late"), connection_id=session.connection_id)
        with recovered.connection_factory.unit_of_work(write=False) as uow:
            current = dispatcher.repo.get(uow, operation_id)
            assert current["status"] == "OUTCOME_UNKNOWN" and current["terminal_event_id"] is None
            assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE operation_id=?", (operation_id,)).fetchone()[0] == 0
            assert uow.connection.execute("SELECT count(*) FROM runtime_results WHERE operation_id IS NULL").fetchone()[0] == 1
    finally:
        shutdown_runtime(dispatcher, recovered.harness_supervisor)
