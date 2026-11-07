"""No-model Codex resume and the trusted Core resume-grant boundary."""

import asyncio
import json
import sys
import time
from dataclasses import replace
from importlib.resources import files

import pytest
from jsonschema import Draft7Validator

from nexus_connector_core import CoreError, ExecutionContext
from nexus_connector_core.models import InstallationCandidate, LaunchIntent, PreparedLaunch
from nexus_connector_core.native.adapter_types import HarnessCapabilities, HarnessSession, NativeAdapterError
from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
from nexus_connector_core.native.runtime_bridge import CodexResumeGrant, CopiedAdapterFactory


def _context():
    return ExecutionContext("srv", "exe", "bind", "agent", "ws", 1, 1, 1,
                            time.monotonic() + 60, frozenset({"runtime.open"}))


def _prepared():
    candidate = InstallationCandidate("codex_app_server", "C:/codex.exe",
                                      "sha256:binary", "explicit", "selected",
                                      version="synthetic", architecture="x86_64")
    intent = LaunchIntent("agent", "ws", "codex_app_server")
    return PreparedLaunch(intent, candidate, ("C:/codex.exe", "app-server"),
                          "C:/workspace", "C:/workspace", "sha256:root",
                          "sha256:profile", ())


def _grant(prepared, session_id, context):
    return CodexResumeGrant(
        "thread-one", session_id, context.server_id, context.executor_id,
        context.binding_id, context.agent_id, context.workspace_id,
        context.session_owner_generation, prepared.candidate.fingerprint,
        prepared.root_fingerprint, prepared.profile_fingerprint, True, True, True)


def test_codex_resume_wire_and_identity(tmp_path):
    peer = tmp_path / "resume_peer.py"
    peer.write_text("""
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    with open("observed.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps(message) + "\\n")
    if method == "initialize":
        print(json.dumps({"id": message["id"], "result": {
            "userAgent": "nexus_connector_core/0.157.0"}}), flush=True)
    elif method == "thread/resume":
        print(json.dumps({"id": message["id"], "result": {
            "thread": {"id": sys.argv[1], "status": {"type": sys.argv[2]}}}}), flush=True)
""", encoding="utf-8")
    connector = CodexAppServerConnector(
        command=(sys.executable, str(peer), "thread-one", "idle"),
        cwd=str(tmp_path), handshake_timeout_s=3)
    try:
        session = connector.start(owning_agent_id="agent", resume_thread_id="thread-one")
        assert session.metadata["thread_id"] == "thread-one"
        assert session.metadata["resumed"] is True
        assert session.metadata["codex_thread_configuration"]["source"] == "thread/resume/response"
        messages = [json.loads(line) for line in
                    (tmp_path / "observed.jsonl").read_text().splitlines()]
        assert [message["method"] for message in messages] == [
            "initialize", "initialized", "thread/resume"]
        assert messages[2]["params"]["threadId"] == "thread-one"
        assert messages[2]["params"]["cwd"] == str(tmp_path)
        bundle = json.loads(files("nexus_connector_core.native").joinpath(
            "codex_app_server_0_157_0.schemas.json").read_text())
        Draft7Validator({"$ref": "#/definitions/ThreadResumeParams",
                         "definitions": bundle["definitions"]}).validate(messages[2]["params"])
    finally:
        connector.close()


@pytest.mark.parametrize("returned_id,status", [
    ("other-thread", "idle"), ("thread-one", "active"),
    ("thread-one", "systemError")])
def test_codex_resume_rejects_mismatch_or_active(tmp_path, returned_id, status):
    peer = tmp_path / "resume_peer.py"
    peer.write_text("""
import json
import sys
for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "initialize":
        print(json.dumps({"id": message["id"], "result": {
            "userAgent": "nexus_connector_core/0.157.0"}}), flush=True)
    elif message.get("method") == "thread/resume":
        print(json.dumps({"id": message["id"], "result": {
            "thread": {"id": sys.argv[1], "status": {"type": sys.argv[2]}}}}), flush=True)
""", encoding="utf-8")
    connector = CodexAppServerConnector(
        command=(sys.executable, str(peer), returned_id, status),
        cwd=str(tmp_path), handshake_timeout_s=3)
    try:
        with pytest.raises(NativeAdapterError):
            connector.start(owning_agent_id="agent", resume_thread_id="thread-one")
        assert not connector._sessions_by_id
    finally:
        connector.close()


def test_codex_resume_rejects_invalid_id_or_start_only_overrides_before_spawn():
    malformed = CodexAppServerConnector()
    with pytest.raises(NativeAdapterError):
        malformed.start(owning_agent_id="agent", resume_thread_id="../other")
    assert malformed._transport is None

    incompatible = CodexAppServerConnector(
        thread_start_overrides={"serviceName": "start-only"})
    with pytest.raises(NativeAdapterError):
        incompatible.start(owning_agent_id="agent", resume_thread_id="thread-one")
    assert incompatible._transport is None


def test_codex_resume_grant_validated_before_native_open(monkeypatch, tmp_path):
    import nexus_connector_core.native.runtime_bridge as bridge_module
    import nexus_connector_core.native.adapters.codex as codex_module

    from nexus_connector_core.profiles import _root_fingerprint
    prepared = replace(_prepared(), cwd=str(tmp_path), requested_root=str(tmp_path),
                       root_fingerprint=_root_fingerprint(tmp_path))
    context = _context()
    seen = []

    class StubCodex:
        def __init__(self, *, command, cwd, env):
            seen.append(("construct", command, cwd))

        def start(self, *, owning_agent_id, resume_thread_id=None):
            seen.append(("start", owning_agent_id, resume_thread_id))
            return HarnessSession("native-session", "codex", owning_agent_id,
                                  "STARTING", HarnessCapabilities(False, None,
                                                                  False, False, True),
                                  "2026-09-25T00:00:00Z")

        def close(self):
            pass

    monkeypatch.setattr(bridge_module, "qualified_build",
                         lambda *args, **kwargs: True)
    monkeypatch.setattr(codex_module, "CodexAppServerConnector", StubCodex)

    async def run():
        async def environment(_prepared):
            return {}

        async def good_grant(p, session_id, c):
            return _grant(p, session_id, c)

        await CopiedAdapterFactory(environment, codex_resume=good_grant).open(
            prepared, "new-session", context, stream_epoch="epoch")
        assert seen[-1] == ("start", "agent", "thread-one")
        seen.clear()

        async def wrong_grant(p, session_id, c):
            return replace(_grant(p, session_id, c), agent_id="other-agent")

        with pytest.raises(CoreError, match="BINDING_NOT_AUTHORIZED"):
            await CopiedAdapterFactory(environment, codex_resume=wrong_grant).open(
                prepared, "new-session", context, stream_epoch="epoch")
        assert not seen

        async def unpersisted_grant(p, session_id, c):
            return replace(_grant(p, session_id, c), persisted_rollout_observed=False)

        with pytest.raises(CoreError, match="BINDING_NOT_AUTHORIZED"):
            await CopiedAdapterFactory(environment, codex_resume=unpersisted_grant).open(
                prepared, "new-session", context, stream_epoch="epoch")
        assert not seen

    asyncio.run(run())
