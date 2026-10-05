"""Gate reprompt on observed Pi settle, with a deterministic native-reader barrier."""
import threading

import pytest

from okto_nexus.domain.harness import HarnessCommand
from okto_nexus.errors import OktoNexusError
from test_harness_pi_connector import (
    connector as connector_fixture, fake_server_script as script_fixture,
    log_path as log_fixture, _collect_until,
)

connector = connector_fixture
fake_server_script = script_fixture
log_path = log_fixture


def test_abort_cannot_reprompt_steer_or_abort_again_before_observed_settle(connector, monkeypatch):
    session = connector.start(owning_agent_id="fixture")
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn",
        payload={"text": "TRIGGER_HOLD_FOR_ABORT fixture"}))
    _collect_until(connector, lambda event: event.native_event == "tool_execution_start", timeout_s=5)
    arrived, release = threading.Event(), threading.Event()
    observe = connector._transport._on_push_event

    def hold_settle(message):
        if message.get("type") == "agent_settled" and not release.is_set():
            arrived.set()
            assert release.wait(10), "fixture must release the observed native frame"
        observe(message)

    monkeypatch.setattr(connector._transport, "_on_push_event", hold_settle)
    outcomes = []

    def interrupt():
        try:
            connector.send(session, HarnessCommand(session_id=session.session_id, verb="interrupt"))
            outcomes.append("returned")
        except Exception as exc:
            outcomes.append(type(exc).__name__)

    worker = threading.Thread(target=interrupt)
    worker.start()
    try:
        assert arrived.wait(5)
        assert worker.is_alive() and outcomes == []
        for verb in ("send_turn", "steer", "interrupt"):
            with pytest.raises(OktoNexusError) as rejected:
                connector.send(session, HarnessCommand(session_id=session.session_id, verb=verb,
                    payload={"text": "too soon"} if verb != "interrupt" else {}))
            assert rejected.value.code == "CONFLICT"
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and outcomes == ["returned"]
    _collect_until(connector, lambda event: event.native_event == "agent_settled", timeout_s=5)
    connector.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn",
        payload={"text": "after observed settle"}))
    completed = _collect_until(connector, lambda event: event.native_event == "agent_settled", timeout_s=5)
    assert completed[-1].native_event == "agent_settled"
