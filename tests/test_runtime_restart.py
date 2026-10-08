"""Recovery uses the production composition and real native fixture pipes."""
import sys
import time

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.harness import build_dispatcher
from legacy_native_fixture.codex import CodexAppServerConnector
from okto_nexus.application.runtime_shutdown import shutdown_runtime
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_pr34_remediation import runtime as runtime_fixture, send_message, open_rest
from test_runtime_outbox import operation, wait_status

runtime = runtime_fixture




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
