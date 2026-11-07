"""Thread-response facts through the real Core event path; no native provider.

The transport below is synthetic and never spawns a process or opens a socket.
It deliberately races notifications before responses and shares a connection.
"""
import asyncio
import copy
import json
import time
from importlib.resources import files

import pytest
from jsonschema import Draft7Validator

from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.journal import SQLiteJournal
from nexus_connector_core.models import (
    EventCursor, ExecutionContext, InstallationCandidate, LaunchIntent,
    OpenOperation, ShutdownPolicy,
)
from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
from nexus_connector_core.native.codex_thread_configuration import (
    EVENT_TYPE, FIELDS, MAX_OBSERVATION_BYTES, METADATA_KEY, observe_thread_response,
)
from nexus_connector_core.native.redaction import NativeSecretRedactor
from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
from nexus_connector_core.protocol import canonical_json
from nexus_connector_core.runtime import LocalRuntimeCore


def response(thread_id="thread-one", **changes):
    return {
        "thread": {"id": thread_id, "status": {"type": "idle"},
                   "turns": [{"input": "PRIVATE_TRANSCRIPT_DO_NOT_COPY"}]},
        "approvalPolicy": "on-request", "approvalsReviewer": "user",
        "cwd": "C:/workspace", "instructionSources": ["C:/workspace/AGENTS.md"],
        "model": "synthetic-model", "modelProvider": "synthetic-provider",
        "sandbox": {"type": "workspaceWrite", "writableRoots": ["C:/workspace"],
                    "networkAccess": False},
        "reasoningEffort": "medium", **changes,
    }


def project(value):
    return observe_thread_response(value, method="thread/start", thread_id="thread-one")


class Transport:
    def __init__(self, connector, responses):
        self.connector = connector
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, params, **_):
        self.calls.append((method, copy.deepcopy(params)))
        if method in {"thread/start", "thread/resume"}:
            result = next(self.responses)
            # Notification arrives while the thread is not registered yet.
            self.connector._on_notification("thread/status/changed", {
                "threadId": result["thread"]["id"], "status": {"type": "idle"}})
            return result
        if method == "model/list":
            return {"data": [], "nextCursor": None}
        if method == "configRequirements/read":
            return {"requirements": None}
        if method == "thread/unsubscribe":
            return {}
        raise AssertionError("unexpected synthetic RPC: " + method)

    def close(self):
        self.connector._closed_event.set()
        return "graceful"


def connector_for(*responses):
    connector = CodexAppServerConnector()
    connector._transport = Transport(connector, responses)
    connector._compatibility_report = {"native_version": "0.157.0"}
    connector.observe_lifecycle = lambda _: {
        "stop_observed": connector._closed_event.is_set(), "active_turn": False}
    return connector


def context():
    return ExecutionContext("server", "executor", "binding", "agent", "workspace",
                            1, 1, 1, time.monotonic() + 60,
                            frozenset({"runtime.open", "runtime.close"}))


def dispose(bridge):
    bridge._control_executor.shutdown()
    bridge._force_executor.shutdown()


def test_response_schema_fields_are_observed_without_transcript_or_defaults():
    value = response(reasoningEffort=None, instructionSources=[],
                     sandbox={"type": "readOnly"},
                     ignoredConfiguration={"content": "PRIVATE_CONFIG"})
    original = copy.deepcopy(value)
    observed = project(value)
    schema = json.loads(files("nexus_connector_core.native").joinpath(
        "codex_app_server_0_157_0.schemas.json").read_text(encoding="utf-8"))
    definitions = schema["definitions"]
    properties = definitions["ThreadStartResponse"]["properties"]
    assert set(observed["fields"]) == set(FIELDS)
    for name in FIELDS:
        field = observed["fields"][name]
        assert field == {"status": "reported", "value": value[name]}
        Draft7Validator({**properties[name], "definitions": definitions}).validate(field["value"])
    assert observed["fields"]["sandbox"]["value"] == {"type": "readOnly"}
    assert "PRIVATE" not in json.dumps(observed)
    assert value == original
    # Detached lists: mutating the upstream response cannot rewrite history.
    value["instructionSources"].append("later.md")
    assert observed["fields"]["instructionSources"]["value"] == []


def test_missing_is_not_empty_null_or_schema_default():
    observed = project({"thread": {"id": "thread-one"}})
    assert observed["fields"] == {key: {"status": "missing"} for key in FIELDS}
    explicit = project({"instructionSources": [], "reasoningEffort": None,
                        "sandbox": {"type": "readOnly"}, "cwd": None})["fields"]
    assert explicit["instructionSources"] == {"status": "reported", "value": []}
    assert explicit["reasoningEffort"] == {"status": "reported", "value": None}
    assert explicit["cwd"] == {"status": "invalid", "reason": "invalid_value"}
    assert "networkAccess" not in explicit["sandbox"]["value"]


@pytest.mark.parametrize("field,value", [
    ("approvalPolicy", {"granular": {"rules": True, "mcp_elicitations": False,
                                     "sandbox_approval": True, "request_permissions": False}}),
    ("sandbox", {"type": "externalSandbox", "networkAccess": "restricted"}),
    ("sandbox", {"type": "dangerFullAccess"}),
    ("sandbox", {"type": "readOnly", "networkAccess": False}),
    ("sandbox", {"type": "workspaceWrite", "writableRoots": [],
                 "excludeSlashTmp": False, "excludeTmpdirEnvVar": True}),
])
def test_policy_variants_preserve_reported_false_and_absent_optional_fields(field, value):
    assert project(response(**{field: value}))["fields"][field] == {
        "status": "reported", "value": value}


@pytest.mark.parametrize("field,value", [
    ("approvalPolicy", "on-failure"),
    ("approvalPolicy", {"granular": {"rules": True}}),
    ("approvalPolicy", {"granular": {"rules": 1, "mcp_elicitations": False, "sandbox_approval": True}}),
    ("approvalsReviewer", "future-reviewer"),
    ("cwd", "relative/path"), ("cwd", "C:drive-relative"),
    ("cwd", "C:/line\nbreak"),
    ("instructionSources", [{"path": "AGENTS.md", "content": "PRIVATE"}]),
    ("instructionSources", None), ("instructionSources", [False]),
    ("model", ""), ("model", True), ("modelProvider", {"token": "PRIVATE"}),
    ("reasoningEffort", 2), ("reasoningEffort", "\ud800"),
    ("sandbox", {"type": "workspaceWrite", "networkAccess": 1}),
    ("sandbox", {"type": "workspaceWrite", "writableRoots": ["relative"]}),
    ("sandbox", {"type": "externalSandbox", "networkAccess": True}),
    ("sandbox", {"type": "future-mode"}),
])
def test_malformed_field_is_explicit_and_does_not_erase_other_facts(field, value):
    observed = project(response(**{field: value}))
    assert observed["fields"][field] == {"status": "invalid", "reason": "invalid_value"}
    unaffected = "model" if field != "model" else "approvalsReviewer"
    assert observed["fields"][unaffected]["status"] == "reported"


@pytest.mark.parametrize("field,value", [
    ("sandbox", {"type": "readOnly", "futureWriteAccess": True}),
    ("sandbox", {"type": "dangerFullAccess", "networkAccess": False}),
    ("approvalPolicy", {"granular": {"rules": True, "mcp_elicitations": False,
                                     "sandbox_approval": True, "future": False}}),
    ("approvalPolicy", {"granular": {"rules": True, "mcp_elicitations": False,
                                     "sandbox_approval": True}, "future": True}),
])
def test_unknown_policy_properties_never_look_like_complete_effective_policy(field, value):
    assert project(response(**{field: value}))["fields"][field] == {
        "status": "invalid", "reason": "unknown_policy_field"}


@pytest.mark.parametrize("field,value", [
    ("model", "x" * 257), ("reasoningEffort", "x" * 65),
    ("modelProvider", "\u00e9" * 129), ("cwd", "/" + "x" * 4096),
    ("instructionSources", ["a"] * 33),
    ("instructionSources", ["/" + "x" * 4095] * 5),
    ("sandbox", {"type": "workspaceWrite", "writableRoots": ["/" + "x" * 4095] * 5}),
], ids=["model", "effort", "provider-utf8", "path", "reference-count", "reference-bytes", "policy-bytes"])
def test_oversize_is_explicit_not_silently_truncated(field, value):
    observed = project(response(**{field: value}))
    assert observed["fields"][field] == {"status": "invalid", "reason": "limit_exceeded"}
    assert len(canonical_json(observed)) <= MAX_OBSERVATION_BYTES


@pytest.mark.asyncio
async def test_bridge_emits_before_discovery_and_masks_secrets_in_valid_references():
    connector = connector_for(response(model="injected-child-credential",
        instructionSources=["C:/nxs_synthetic_only/AGENTS.md"],
        sandbox={"type": "workspaceWrite", "writableRoots": ["C:/injected-child-credential"]}))
    session = connector.start(owning_agent_id="agent")
    bridge = CopiedAdapterSession(connector, session, session_id="public-session",
        stream_epoch="epoch", context=context(),
        redactor=NativeSecretRedactor(["injected-child-credential", "model"]))
    stream = bridge.events()
    try:
        event = await anext(stream)
        assert event.native_type == EVENT_TYPE and event.category == "lifecycle"
        assert event.operation_id is None
        assert event.payload["source"] == "thread/start/response"
        assert [call[0] for call in connector._transport.calls] == ["thread/start"]
        for field in ("model", "instructionSources", "sandbox"):
            assert event.payload["fields"][field] == {"status": "invalid", "reason": "redacted"}
        assert "injected-child-credential" not in str(event)
        assert "nxs_" not in str(event)
        assert "PRIVATE" not in str(event)
        # Existing discovery continues; no additional RPC was added.
        assert (await anext(stream)).native_type == "core/harness_configuration"
        assert [call[0] for call in connector._transport.calls] == [
            "thread/start", "model/list", "configRequirements/read"]
    finally:
        await stream.aclose()
        connector.close()
        dispose(bridge)


@pytest.mark.asyncio
async def test_two_sessions_reverse_consumption_and_resume_keep_response_scope():
    first = response("thread-first", model="first-model")
    resumed = response("thread-resumed", model="resumed-model",
                       approvalsReviewer="auto_review", instructionSources=["other/AGENTS.md"])
    connector = connector_for(first, resumed)
    sessions = [connector.start(owning_agent_id="first-agent"),
                connector.start(owning_agent_id="second-agent", resume_thread_id="thread-resumed")]
    bridges = [CopiedAdapterSession(connector, session, session_id=f"public-{i}",
               stream_epoch=f"epoch-{i}", context=context()) for i, session in enumerate(sessions)]
    try:
        for i in (1, 0):
            stream = bridges[i].events()
            try:
                observed = await anext(stream)
                assert (observed.session_id, observed.stream_epoch) == (f"public-{i}", f"epoch-{i}")
                assert observed.payload["source"] == ("thread/resume/response" if i else "thread/start/response")
                assert observed.payload["thread_id"] == ("thread-resumed" if i else "thread-first")
                assert observed.payload["fields"]["model"]["value"] == ("resumed-model" if i else "first-model")
                await anext(stream)  # Existing discovery; then the early notification.
                early = await anext(stream)
                assert early.native_type == "thread/status/changed"
                assert early.session_id == observed.session_id
                assert early.payload["thread_id"] == observed.payload["thread_id"]
            finally:
                await stream.aclose()
        first["model"] = "changed-after-response"
        assert sessions[0].metadata[METADATA_KEY]["fields"]["model"]["value"] == "first-model"
    finally:
        connector.close()
        for bridge in bridges:
            dispose(bridge)


@pytest.mark.asyncio
async def test_bridge_observation_is_durable_session_scoped_core_event(tmp_path):
    """Real open/event pump/journal/replay, with a synthetic in-memory transport."""
    binary = tmp_path / "synthetic-codex"
    binary.write_bytes(b"synthetic: never executed")
    connector = connector_for(response(model="child-secret"))
    bridges = []

    class Factory:
        async def open(self, prepared, session_id, authority, *, stream_epoch):
            session = connector.start(owning_agent_id=authority.agent_id)
            bridge = CopiedAdapterSession(connector, session, session_id=session_id,
                stream_epoch=stream_epoch, context=authority,
                redactor=NativeSecretRedactor(["child-secret"]))
            bridges.append(bridge)
            return bridge

    path = tmp_path / "journal.db"
    journal = SQLiteJournal(path)
    candidate = InstallationCandidate("codex_app_server", str(binary), fingerprint(binary),
                                      "explicit", "selected")
    runtime = LocalRuntimeCore(journal, Factory(), candidates={"codex_app_server": candidate},
                               workspace_roots={"workspace": str(tmp_path)})
    cursor = EventCursor("server", "executor", "public-session", "public-epoch")
    try:
        prepared = await runtime.prepare(LaunchIntent("agent", "workspace", "codex_app_server"), context())
        receipt = await runtime.open(OpenOperation("opening", "public-session", "public-epoch", prepared), context())
        assert receipt.stage == "SUBMITTED"
        stream = runtime.events(cursor)
        event = await asyncio.wait_for(anext(stream), 3)
        await stream.aclose()
        assert event.native_type == EVENT_TYPE and event.category == "lifecycle"
        assert (event.server_id, event.executor_id, event.session_id, event.stream_epoch) == (
            "server", "executor", "public-session", "public-epoch")
        assert event.sequence == 1
        assert event.payload["fields"]["model"] == {"status": "invalid", "reason": "redacted"}
        replay = [item async for item in journal.events(cursor)]
        assert replay[0] == event
        assert not [item async for item in journal.events(EventCursor("other", "executor", "public-session", "public-epoch"))]
    finally:
        await runtime.shutdown(ShutdownPolicy(1, 1))
        connector.close()
        for bridge in bridges:
            dispose(bridge)
        journal.close()
    # The observation survives reopening storage and does not depend on a live
    # adapter, native event queue or a second observation RPC.
    reopened = SQLiteJournal(path)
    try:
        replay = [item async for item in reopened.events(cursor)]
        assert replay[0] == event
        persisted = json.dumps([item.payload for item in replay])
        assert "child-secret" not in persisted and "PRIVATE_TRANSCRIPT" not in persisted
    finally:
        reopened.close()
