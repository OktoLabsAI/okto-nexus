"""Known approved backend credentials must not become native diagnostic output."""
import json
import sys

import pytest

from legacy_native_fixture.codex import CodexAppServerConnector
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
    from legacy_native_fixture.event_buffers import NativeEventOverflow, NativeReplayExpired, NativeSubscriptionLimit
    from legacy_native_fixture.framing import FrameLimitExceeded
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
