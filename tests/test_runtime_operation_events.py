"""Public operation states follow durable events without native status polling."""
import threading

from okto_nexus.adapters.outbound.harness.codex import _CodexTransport
from test_pr34_remediation import runtime as runtime_fixture, open_rest, tool
from test_runtime_commands import codex_session

runtime = runtime_fixture


def test_queued_and_unconfirmed_operation_are_distinct_without_invented_result(runtime, monkeypatch):
    deps, client, _, peers, operator, _ = runtime
    sid = open_rest(runtime).json()["data"]["session_id"]
    runner = deps.runtime_dispatcher.command_dispatcher
    execute = runner._execute
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def held(command, control):
        entered.set()
        assert release.wait(8)
        try:
            return execute(command, control)
        finally:
            finished.set()

    monkeypatch.setattr(runner, "_execute", held)
    try:
        admitted = tool(client, operator, "harness_send", {
            "session_id": sid, "payload": {"text": "unconfirmed fixture"}, "idempotency_key": "state-fixture"})
        assert admitted["ok"], admitted
        assert admitted["data"]["state"] == "PENDING" and admitted["data"]["durable"]
        assert admitted["data"]["external_acceptance"] == "not_observed"
        assert entered.wait(5) and peers[0].sent == []
    finally:
        release.set()
    assert finished.wait(5)
    op = admitted["data"]["operation_id"]
    observed = tool(client, operator, "harness_get", {"operation_id": op})
    assert observed["ok"] and observed["data"]["state"] == "SENT_UNCONFIRMED", observed
    assert observed["data"]["external_acceptance"] == "not_observed"
    assert not observed["data"]["result_durable"] and observed["data"]["result"] is None
    assert len(peers[0].sent) == 1


def test_accepted_and_final_operation_follow_push_and_public_replay(runtime, monkeypatch):
    deps, client, _, _, operator, _ = runtime
    sid = codex_session(runtime)
    started, terminal = threading.Event(), threading.Event()
    captured, methods = [], []
    write = _CodexTransport._write

    def observed_write(self, payload):
        if "method" in payload:
            methods.append(payload["method"])
        return write(self, payload)

    monkeypatch.setattr(_CodexTransport, "_write", observed_write)

    def on_event(event):
        if event.operation_id:
            captured.append(event)
            if event.delivery_phase == "started":
                started.set()
            if event.delivery_phase == "terminal":
                terminal.set()

    handle = deps.harness_supervisor.subscribers.subscribe(sid, on_event)
    try:
        admitted = tool(client, operator, "harness_send", {
            "session_id": sid, "payload": {"text": "TRIGGER_HOLD"}, "idempotency_key": "observed-state"})
        assert admitted["ok"] and admitted["data"]["state"] == "PENDING", admitted
        op = admitted["data"]["operation_id"]
        assert started.wait(6), "native event was not durably projected and pushed"
        accepted = tool(client, operator, "harness_get", {"operation_id": op})
        assert accepted["ok"] and accepted["data"]["state"] == "ACCEPTED", accepted
        assert accepted["data"]["external_acceptance"] == "harness_accepted"
        assert not accepted["data"]["result_durable"] and accepted["data"]["result"] is None
        interrupted = tool(client, operator, "harness_interrupt", {"session_id": sid,
            "expected_operation_id": op, "expected_turn_id": accepted["data"]["native_turn_id"]})
        assert interrupted["ok"], interrupted
        assert terminal.wait(6)
        final = client.get(f"/api/v1/harness/operations/{op}", headers={"x-api-key": operator})
        assert final.status_code == 200, final.text
        data = final.json()["data"]
        assert data["operation_id"] == op and data["result_durable"] and data["result"]
        replay = tool(client, operator, "harness_event_list", {"session_id": sid, "limit": 200})
        assert replay["ok"], replay
        events = [e for e in replay["data"]["events"] if e["operation_id"] == op]
        phases = {e["delivery_phase"] for e in events}
        assert {"started", "terminal"} <= phases
        assert {e.event_id for e in captured if e.operation_id == op} <= {e["event_id"] for e in events}
        assert all(e["attempt_id"] == data["attempt_id"] and e["sequence"] for e in events)
        # After handshake, these are the only native outbound methods. State
        # progression waited for pushed events, never a native status query.
        assert methods == ["turn/start", "turn/interrupt"]
    finally:
        deps.harness_supervisor.subscribers.unsubscribe(handle)
