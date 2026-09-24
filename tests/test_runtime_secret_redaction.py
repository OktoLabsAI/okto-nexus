"""Known approved backend credentials must not become native diagnostic output."""
import json
import sys

import pytest

from okto_nexus.adapters.outbound.harness.codex import CodexAppServerConnector
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_harness_tools import FakeConnector
from test_pr34_remediation import runtime as runtime_fixture, tool
from test_runtime_commands import wait_operation

runtime = runtime_fixture
SECRET = "fixture-opaque-backend-credential-43816"


def configure_secret(runtime, monkeypatch, profile_id="profile-codex"):
    _, client, _, _, operator, _ = runtime
    monkeypatch.setenv("FIXTURE_BACKEND_CREDENTIAL_SOURCE", SECRET)
    response = client.patch("/api/v1/harness/profiles/" + profile_id,
        headers={"x-api-key": operator}, json={"expected_revision": 1,
            "secret_refs": {"FIXTURE_BACKEND_KEY": "env:FIXTURE_BACKEND_CREDENTIAL_SOURCE"}})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("fragmentation", ["single", "split", "characters"])
def test_resolved_secret_is_redacted_before_journal_result_and_replay(runtime, monkeypatch, caplog, fragmentation):
    deps, client, root, _, operator, _ = runtime
    configure_secret(runtime, monkeypatch)
    original = next(line for line in _FAKE_SERVER_SOURCE.splitlines() if '"delta": text' in line)
    fragments = {"single": '["safe before " + value + " safe after"]',
        "split": '["safe before " + value[:17], value[17:] + " safe after"]',
        "characters": '["safe before "] + list(value) + [" safe after"]'}[fragmentation]
    source = _FAKE_SERVER_SOURCE.replace(original,
        '    value = os.environ["FIXTURE_BACKEND_KEY"]\n'
        '    for fragment in ' + fragments + ':\n' + original.replace('"delta": text', '"delta": fragment').replace('    write_msg', '        write_msg'))
    assert source != _FAKE_SERVER_SOURCE
    deps.harness_connector_factories["codex"] = lambda **options: CodexAppServerConnector(
        command=[sys._base_executable, "-u", "-c", source], cwd=root, env=options["backend"]["env"])
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 200, opened.text
    sid = opened.json()["data"]["session_id"]
    assert deps.harness_supervisor._live[sid].connector.native._env["FIXTURE_BACKEND_KEY"] == SECRET
    assert opened.json()["data"]["compatibility_report"]["backend_secret_redaction"]["version"] == 2
    for index in range(2):
        sent = tool(client, operator, "harness_send", {"session_id": sid, "payload": {"text": f"fixture diagnostic {index}"}})
        assert sent["ok"], sent
        result = wait_operation(runtime, sent["data"]["operation_id"], lambda row: row["result_durable"])
        assert result["result"]["output_text"] == "safe before [REDACTED] safe after"
    journal = deps.harness_supervisor.event_ingress.journal
    assert SECRET.encode() not in b"".join(path.read_bytes() for path in journal.root.glob("segment-*.bin"))
    replay = tool(client, operator, "harness_event_list", {"session_id": sid})
    assert replay["ok"], replay
    assert SECRET not in json.dumps(replay)
    assert SECRET not in caplog.text
    # Reassembling raw delta payloads must not defeat normalized output scrubbing.
    events = deps.harness_supervisor.replay_events(sid)
    assert SECRET not in "".join(str(event.payload.get("delta", "")) for event in events)


def test_redaction_preserves_no_write_proof_and_retry_classification():
    from okto_nexus.adapters.outbound.harness.secret_redaction import BackendSecretRedactor
    from okto_nexus.domain.runtime_commands import RuntimeCommandNotSent, RuntimeLaneBusyBeforeWrite
    from okto_nexus.errors import ErrorCode, OktoNexusError
    redactor = BackendSecretRedactor([SECRET])
    for cls in (RuntimeCommandNotSent, RuntimeLaneBusyBeforeWrite):
        cleaned = redactor.error(cls("denied " + SECRET))
        assert type(cleaned) is cls and SECRET not in str(cleaned)
    unknown = redactor.error(OSError("write outcome unknown " + SECRET))
    assert isinstance(unknown, OktoNexusError) and unknown.code == ErrorCode.INTERNAL_ERROR
    assert not isinstance(unknown, RuntimeCommandNotSent) and not unknown.retryable


def test_redaction_preserves_local_gap_and_overflow_evidence_types():
    from okto_nexus.adapters.outbound.harness.secret_redaction import BackendSecretRedactor
    from okto_nexus.adapters.outbound.harness.event_buffers import NativeEventOverflow, NativeReplayExpired, NativeSubscriptionLimit
    from okto_nexus.adapters.outbound.harness.framing import FrameLimitExceeded
    redactor = BackendSecretRedactor([SECRET])
    for cls in (NativeEventOverflow, NativeReplayExpired, FrameLimitExceeded):
        assert type(redactor.error(cls())) is cls
    limited = redactor.error(NativeSubscriptionLimit("capacity " + SECRET))
    assert type(limited) is NativeSubscriptionLimit and SECRET not in str(limited)


def test_snapshot_output_and_native_approval_keep_original_correlation():
    from dataclasses import replace
    from okto_nexus.adapters.outbound.harness.secret_redaction import BackendSecretRedactor
    from okto_nexus.domain.harness import HarnessEvent
    redactor = BackendSecretRedactor([SECRET])
    event = HarnessEvent(session_id="fixture-session", harness_kind="claude_code", kind="output_delta",
        native_event="assistant", occurred_at="fixture", operation_id="fixture-operation",
        attempt_id="fixture-attempt", owner_epoch=3, output_text=SECRET[:17], output_snapshot=True,
        payload={"text": SECRET[:17], "type": "assistant"})
    approval = replace(event, kind="tool_activity", native_event="control_request", output_text=None,
        output_snapshot=False, native_approval={"request_id": "fixture-request", "request_hash": "fixed-original-hash",
            "params": {"command": "fixture-command " + SECRET}})
    terminal = replace(event, kind="turn_completed", native_event="result:success", delivery_phase="terminal",
        output_text="complete " + SECRET, payload={"result": "complete " + SECRET})
    recorded = list(redactor.events(iter([event, approval, terminal])))
    assert recorded[-1].output_text == "complete [REDACTED]" and recorded[-1].output_snapshot
    assert recorded[1].native_approval["request_id"] == "fixture-request"
    assert recorded[1].native_approval["request_hash"] == "fixed-original-hash"
    assert SECRET not in json.dumps(recorded[1].native_approval)
    assert all(e.operation_id == "fixture-operation" and e.attempt_id == "fixture-attempt" and e.owner_epoch == 3 for e in recorded)


def test_redaction_is_scoped_to_effective_profile_and_handles_encoded_diagnostics():
    from okto_nexus.adapters.outbound.harness.secret_redaction import BackendSecretRedactor
    value = 'fixture-quote-"-and-\\-secret'
    profile = {"secret_refs": {"CUSTOM_FIELD": "env:APPROVED_SOURCE"}, "inherit_ambient": False}
    redactor = BackendSecretRedactor.from_environment(profile, {"CUSTOM_FIELD": value, "UNRELATED_TOKEN": SECRET})
    assert redactor.clean(json.dumps({"diagnostic": value})) == '{"diagnostic": "[REDACTED]"}'
    assert redactor.clean(SECRET) == SECRET, "Unrelated ambient configuration must not enter the profile scope"
    inherited = BackendSecretRedactor.from_environment(profile | {"inherit_ambient": True}, {"UNRELATED_TOKEN": SECRET})
    assert inherited.clean(SECRET) == "[REDACTED]"


@pytest.mark.parametrize("values", [["x" * 16385], ["fixture-" + str(i) for i in range(129)]])
def test_excessive_secret_scope_fails_closed_before_native_construction(values):
    from okto_nexus.adapters.outbound.harness.secret_redaction import BackendSecretRedactor
    from okto_nexus.errors import OktoNexusError
    with pytest.raises(OktoNexusError, match="bounded capacity"):
        BackendSecretRedactor(values)


@pytest.mark.parametrize("boundary", ["construct", "start"])
def test_resolved_secret_is_not_exposed_by_native_start_errors(runtime, monkeypatch, caplog, boundary):
    deps, client, root, _, operator, _ = runtime
    configure_secret(runtime, monkeypatch)

    def factory(**options):
        value = options["backend"]["env"]["FIXTURE_BACKEND_KEY"]
        if boundary == "construct":
            raise RuntimeError("fixture constructor diagnostic " + value)
        peer = FakeConnector(kind="codex")
        def start(**kwargs):
            raise RuntimeError("fixture handshake diagnostic " + value)
        peer.start = start
        return peer

    deps.harness_connector_factories["codex"] = factory
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": "worker", "kind": "codex", "endpoint_id": "endpoint-codex", "project_root": root})
    assert opened.status_code == 500, opened.text
    assert SECRET not in opened.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("kind", ["codex", "claude_code"])
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_secret_in_native_approval_is_private_without_breaking_exact_reply(runtime, monkeypatch, kind, decision):
    from test_pr34_remediation import send_message
    from test_runtime_native_approvals import approval_peer, pending
    from test_runtime_claude_approvals import claude_peer, PEER
    from test_runtime_handoff_dispatch import wait_result
    deps, client, _, _, operator, caller = runtime
    configure_secret(runtime, monkeypatch,
        "profile-codex" if kind == "codex" else "profile-claude_code.stream")
    if kind == "codex":
        sid = approval_peer(runtime, extra_params={"command": "fixture-command " + SECRET})
    else:
        source = PEER.replace("import json,sys", "import json,sys,os").replace(
            '"content":"fixture"', '"content":os.environ["FIXTURE_BACKEND_KEY"]')
        sid = claude_peer(runtime, source)
    sent = send_message(runtime, body="TRIGGER_SERVER_REQUEST")
    request = pending(runtime)
    assert SECRET not in json.dumps(request)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        observed = dict(uow.connection.execute("SELECT * FROM runtime_native_approvals").fetchone())
    assert SECRET not in json.dumps(observed)
    url = f"/api/v1/approvals/{request['approval_id']}/decision"
    assert client.post(url, headers={"x-api-key": caller}, json={"decision": decision}).status_code == 403
    decided = client.post(url, headers={"x-api-key": operator}, json={"decision": decision})
    assert decided.status_code == 200, decided.text
    result = wait_result(runtime, sent["runtime_operations"][0])
    wire = json.loads(result["output_text"])
    if kind == "codex":
        assert wire["id"] == 9001
        assert wire["result"]["decision"] == ("accept" if decision == "approve" else "decline")
    else:
        assert wire["response"]["request_id"] == "permission-1"
        assert wire["response"]["response"]["behavior"] == ("allow" if decision == "approve" else "deny")
    assert SECRET not in result["output_text"]
    replay = tool(client, operator, "harness_event_list", {"session_id": sid})
    assert replay["ok"] and SECRET not in json.dumps(replay)


def test_secret_stream_budget_is_finite_and_failure_does_not_claim_terminal():
    from okto_nexus.adapters.outbound.harness.secret_redaction import BackendSecretRedactor
    from okto_nexus.domain.harness import HarnessEvent
    from okto_nexus.errors import OktoNexusError
    redactor = BackendSecretRedactor([SECRET])
    events = (HarnessEvent(session_id="fixture", harness_kind="codex", kind="output_delta",
        native_event="fixture/delta", occurred_at="fixture", output_text=SECRET[:5],
        operation_id="unmatched-" + str(index)) for index in range(65))
    recorded = []
    with pytest.raises(OktoNexusError, match="stream capacity"):
        recorded.extend(redactor.events(events))
    assert len(recorded) == 64
    assert all(event.delivery_phase is None and event.output_text == "" for event in recorded)


def test_native_payload_cannot_assert_server_redaction_policy():
    from okto_nexus.adapters.outbound.harness.secret_redaction import BackendSecretRedactor
    from okto_nexus.domain.harness import HarnessEvent
    event = HarnessEvent(session_id="fixture", harness_kind="codex", kind="tool_activity",
        native_event="fixture/observation", occurred_at="fixture",
        payload={"_nexus_redaction": {"version": 999, "raw_text": "safe-by-payload"}})
    plain = list(BackendSecretRedactor().events(iter([event])))[0]
    assert "_nexus_redaction" not in plain.payload
    protected = list(BackendSecretRedactor([SECRET]).events(iter([event])))[0]
    assert protected.payload["_nexus_redaction"]["version"] == 2
