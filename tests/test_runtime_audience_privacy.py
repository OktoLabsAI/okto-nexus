"""Runtime delivery and result projection obey both private scope directions."""
import json
import threading

import pytest

from okto_nexus.application.runtime_results import RuntimeResultService
from test_pr34_remediation import runtime as runtime_fixture, send_message, tool
from test_runtime_commands import codex_session
from test_runtime_result_publication import result

runtime = runtime_fixture


@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_scope_exclusions_apply_to_delivery_and_result_without_disclosing_policy(runtime, monkeypatch, direction):
    deps, client, root, _, operator, caller = runtime
    headers = {"x-api-key": operator}
    tag = "private_runtime_audience"
    assert client.post("/api/v1/tags", headers=headers, json={"key": tag}).status_code == 200
    for value in ("allowed", "excluded-private-rule"):
        assert client.post(f"/api/v1/tags/{tag}/values", headers=headers, json={"value": value}).status_code == 200
    for agent in ("worker", "caller"):
        response = client.patch(f"/api/v1/agents/{agent}", headers=headers, json={"tags": {tag: ["allowed"]}})
        assert response.status_code == 200, response.text
    sid = codex_session(runtime)

    def scope(agent, value):
        response = client.patch(f"/api/v1/agents/{agent}", headers=headers,
            json={"comm_scope": {direction: {tag: [value]}}})
        assert response.status_code == 200, response.text

    admission_actor = "worker" if direction == "inbound" else "caller"
    scope(admission_actor, "excluded-private-rule")
    denied = tool(client, caller, "message_create", {"project_root": root, "from_agent_id": "caller",
        "target": {"strategy": "direct", "agent_id": "worker"}, "body": "excluded input", "subject": "audience"})
    assert denied.get("error", {}).get("code") == "PERMISSION_DENIED", denied
    assert tag not in json.dumps(denied) and "excluded-private-rule" not in json.dumps(denied)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 0
        assert uow.connection.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
    assert not any(e.native_event == "turn/started" for e in deps.harness_supervisor.replay_events(sid))

    # Positive input control, followed by a policy change before the canonical
    # result publisher authorizes its reverse audience. No writer is held.
    scope(admission_actor, "allowed")
    entered, release = threading.Event(), threading.Event()
    prepare = RuntimeResultService.prepare

    def held(self, result_id, **kwargs):
        entered.set()
        assert release.wait(10)
        return prepare(self, result_id, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(RuntimeResultService, "prepare", held)
        try:
            sent = send_message(runtime, body="retained private result")
            assert entered.wait(6)
            publication_actor = "caller" if direction == "inbound" else "worker"
            scope(publication_actor, "excluded-private-rule")
        finally:
            release.set()
        stored = result(runtime, sent["runtime_operations"][0], "BLOCKED")
    assert "retained private result" in stored["output_text"]
    assert not stored["publication_message_id"]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT count(*) FROM delivery_outbox").fetchone()[0] == 1
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE subject='Runtime result'").fetchone()[0] == 0
        envelope = uow.connection.execute("SELECT envelope FROM delivery_outbox").fetchone()[0]
    assert tag not in envelope and "excluded-private-rule" not in envelope and "comm_scope" not in envelope
    assert tag not in stored["output_text"] and "excluded-private-rule" not in stored["output_text"]
    assert sum(e.native_event == "turn/started" for e in deps.harness_supervisor.replay_events(sid)) == 1
