"""Optional two-application HTTP inventory and receipt conformance.

Set OKTO_CONNECTOR_SRC to the Connector's src directory. This exercises the
real Nexus ASGI router and Connector HTTP client against the same Core wheel;
it is a contract test, not provider or two-host evidence.
"""

from __future__ import annotations

import os
import asyncio
import time
from pathlib import Path

import httpx
import pytest
from nexus_connector_core import (
    CloseOperation, ControlOperation, ExecutionContext, InstallationCandidate, LaunchIntent,
    OpenOperation, R4_PREVIEW_REVISION, ShutdownPolicy, TurnOperation,
    create_runtime, r4_submit_intent_hash,
)
from nexus_connector_core.discovery import fingerprint
from nexus_connector_core.journal import SQLiteJournal

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap


class _Native:
    native_id = "synthetic-native"
    active_turn_id = "turn-from-native"

    def __init__(self):
        self.queue = asyncio.Queue()
        self.stopped = False
        self.sent = []

    async def send(self, verb, payload, operation_id, *, expected_turn_id=None):
        self.sent.append((verb, operation_id))

    async def events(self):
        while True:
            event = await self.queue.get()
            if event is None:
                return
            yield event

    async def close(self):
        self.stopped = True
        await self.queue.put(None)
        return "graceful"

    async def observe(self):
        return ("STOPPED" if self.stopped else "RUNNING", "IDLE")


class _NativeFactory:
    def __init__(self):
        self.native = _Native()

    async def open(self, prepared, session_id, context, *, stream_epoch):
        return self.native


def test_connector_publishes_core_snapshot_to_nexus(tmp_path, monkeypatch):
    source = os.environ.get("OKTO_CONNECTOR_SRC")
    if not source or not Path(source).is_dir():
        pytest.skip("Set OKTO_CONNECTOR_SRC for the cross-repo contract run")
    monkeypatch.syspath_prepend(source)
    from okto_nexus_connector.services.discovery_service import (
        executor_inventory_snapshot,
    )
    from okto_nexus_connector.services.realization_service import (
        publish_local_realization,
    )
    from okto_nexus_connector.storage.state_store import StateStore
    from okto_nexus_connector.transport.https_client import NexusHTTPClient

    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
            ("agent-a", "2026-09-29T00:00:00Z"),
        )
    with deps.connection_factory.unit_of_work() as uow:
        key = app.state.auth.issue_key(uow, agent_id="agent-a")
    async def roundtrip():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport) as raw:
            async with NexusHTTPClient("http://127.0.0.1:8202", client=raw) as http:
                me = await http.me(key)
                assert me.agent_id == "agent-a"
                registered = await http.register_executor(
                    key, client_intent_id="register-a", connector_id="connector-a",
                    label="Remote host",
                )
                assert registered.server_id == me.server_id
                binary = tmp_path / "synthetic-codex.exe"
                binary.write_bytes(b"synthetic Core candidate")
                candidate = InstallationCandidate(
                    "codex_app_server", str(binary), fingerprint(binary),
                    "explicit", "selected")
                snapshot = executor_inventory_snapshot(
                    [candidate], server_id=registered.server_id,
                    executor_id=registered.executor_id,
                    producer_instance_id="connector-process-a",
                    publication_sequence=1,
                )
                accepted = await http.publish_inventory(
                    registered.bootstrap_ticket,
                    executor_id=registered.executor_id, snapshot=snapshot,
                )
                assert accepted.inventory_revision == snapshot["inventory_revision"]
                with deps.connection_factory.unit_of_work() as uow:
                    uow.connection.execute(
                        "INSERT INTO workspaces(workspace_id,created_at) VALUES ('ws',?)",
                        ("2026-09-29T00:00:00Z",),
                    )
                local_store = StateStore(tmp_path / "connector-state.json")
                realization = await publish_local_realization(
                    local_store, http, registered.bootstrap_ticket,
                    server_id=registered.server_id,
                    executor_id=registered.executor_id, agent_id="agent-a",
                    client_intent_id="realization-one", candidates=[candidate],
                    adapter_id="codex_app_server",
                    candidate_ref=snapshot["evidence"][0]["candidate_ref"],
                    inventory_revision=snapshot["inventory_revision"],
                    workspace_root=tmp_path, workspace_id="ws",
                    workspace_label="Project Alpha",
                    configuration_digest="sha256:" + "c" * 64,
                    local_consent_id="consent-one",
                )
                assert realization.agent_id == "agent-a"
                local_record = local_store.load().realizations[0]
                assert local_record.realization_ref == realization.realization_ref
                assert local_record.workspace_root == str(tmp_path.resolve())
                proposal = await http.prepare_r4_binding(
                    key, client_intent_id="binding-prepare-one",
                    executor_id=registered.executor_id,
                    adapter_id="codex_app_server",
                    candidate_ref=snapshot["evidence"][0]["candidate_ref"],
                    inventory_revision=snapshot["inventory_revision"],
                    realization_ref=realization.realization_ref,
                    workspace_id="ws", alias="assistant-alpha",
                    agent_id_hint="agent-a",
                )
                assert proposal.can_apply
                binding = await http.apply_r4_binding(
                    key, client_intent_id="binding-apply-one",
                    proposal=proposal)
                assert binding.binding_id == proposal.binding_id
                submit_frame = {
                    "protocol_major": 1,
                    "contract_revision": R4_PREVIEW_REVISION,
                    "type": "operation.submit", "server_id": me.server_id,
                    "executor_id": registered.executor_id,
                    "binding_id": proposal.binding_id, "agent_id": "agent-a",
                    "workspace_id": "ws",
                    "workspace_binding_id": realization.workspace_binding_id,
                    "session_id": "session", "session_owner_generation": 1,
                    "authorization_revision": binding.authorization_revision,
                    "configuration_revision": binding.configuration_revision,
                    "binding_revision": 1, "credential_epoch": 1,
                    "connection_id": "control", "connection_generation": 1,
                    "grant_id": "grant", "operation_id": "op",
                    "action": "turn.submit", "payload": {"text": "Hello"},
                }
                submit_frame["intent_hash"] = r4_submit_intent_hash(submit_frame)
                steer_frame = {
                    **submit_frame, "operation_id": "steer-op",
                    "action": "turn.steer", "payload": {"text": "Continue"},
                    "expected_turn_id": "turn-from-native",
                }
                steer_frame["intent_hash"] = r4_submit_intent_hash(steer_frame)
                interrupt_frame = {
                    **submit_frame, "operation_id": "interrupt-op",
                    "action": "turn.interrupt",
                    "payload": {"reason": "Requested by the agent"},
                    "expected_turn_id": "turn-from-native",
                }
                interrupt_frame["intent_hash"] = r4_submit_intent_hash(
                    interrupt_frame)
                close_frame = {
                    **submit_frame, "operation_id": "close-op",
                    "action": "runtime.close",
                    "payload": {"reason": "Requested by the agent"},
                }
                close_frame["intent_hash"] = r4_submit_intent_hash(close_frame)
                context = ExecutionContext(
                    me.server_id, registered.executor_id, proposal.binding_id,
                    "agent-a", "ws", binding.authorization_revision,
                    binding.configuration_revision, 1, time.monotonic() + 60,
                    frozenset({"turn.submit"}),
                )
                with deps.connection_factory.unit_of_work() as uow:
                    conn = uow.connection
                    now = "2026-09-29T00:00:00Z"
                    conn.execute(
                        "INSERT INTO execution_operations(server_id,executor_id,operation_id,"
                        "subject_agent_id,actor_agent_id,binding_id,workspace_id,"
                        "workspace_binding_id,session_id,action,intent_hash,semantic_payload,"
                        "expected_revisions_json,admission_state,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (me.server_id, registered.executor_id, "op", "agent-a",
                         "agent-a", proposal.binding_id, "ws",
                         realization.workspace_binding_id,
                         "session", "turn.submit", submit_frame["intent_hash"],
                         "{}", "{}", "ACCEPTED", now),
                    )
                    for operation_id, action, frame in (
                        ("interrupt-op", "turn.interrupt", interrupt_frame),
                        ("close-op", "runtime.close", close_frame),
                    ):
                        conn.execute(
                            "INSERT INTO execution_operations(server_id,executor_id,"
                            "operation_id,subject_agent_id,actor_agent_id,binding_id,"
                            "workspace_id,workspace_binding_id,session_id,action,"
                            "intent_hash,semantic_payload,expected_revisions_json,"
                            "admission_state,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (me.server_id, registered.executor_id, operation_id,
                             "agent-a", "agent-a", proposal.binding_id, "ws",
                             realization.workspace_binding_id, "session", action,
                             frame["intent_hash"], "{}", "{}", "ACCEPTED", now),
                        )
                    conn.execute(
                        "INSERT INTO execution_operations(server_id,executor_id,operation_id,"
                        "subject_agent_id,actor_agent_id,binding_id,workspace_id,"
                        "workspace_binding_id,session_id,action,intent_hash,semantic_payload,"
                        "expected_revisions_json,admission_state,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (me.server_id, registered.executor_id, "steer-op", "agent-a",
                          "agent-a", proposal.binding_id, "ws",
                          realization.workspace_binding_id,
                         "session", "turn.steer", steer_frame["intent_hash"],
                         "{}", "{}", "ACCEPTED", now),
                    )
                ticket = await http.request_r4_binding_ticket(
                    key, binding_id=proposal.binding_id,
                    client_intent_id="ticket-intent",
                    credential_request_id="ticket-request",
                    scopes=("receipt:publish",),
                )
                journal = await asyncio.to_thread(
                    SQLiteJournal, tmp_path / "connector-core.db")
                native_factory = _NativeFactory()

                async def environment(_launch):
                    return {}

                runtime = create_runtime(
                    journal=journal, environment=environment,
                    candidates={"codex_app_server": candidate},
                    workspace_roots={"ws": str(tmp_path)},
                    native_factory=native_factory)
                try:
                    opening_context = ExecutionContext(
                        me.server_id, registered.executor_id,
                        proposal.binding_id,
                        "agent-a", "ws", binding.authorization_revision,
                        binding.configuration_revision, 1,
                        context.lease_deadline_monotonic,
                        frozenset({"runtime.open", "turn.submit", "turn.steer",
                                   "turn.interrupt",
                                   "runtime.close"}),
                    )
                    prepared = await runtime.prepare(
                        LaunchIntent("agent-a", "ws", "codex_app_server"),
                        opening_context)
                    await runtime.open(OpenOperation(
                        "open-op", "session", "stream", prepared),
                        opening_context)
                    core_receipt = await runtime.submit(
                        TurnOperation("op", "session", "Hello"),
                        opening_context)
                    assert native_factory.native.sent == [("send_turn", "op")]
                    receipt_ack = await http.publish_core_turn_receipt(
                        ticket.ticket, submit_frame=submit_frame,
                        core_receipt=core_receipt, context=opening_context,
                        receipt_revision=1)
                    steer_receipt = await runtime.control(
                        ControlOperation("steer-op", "session", "steer",
                                         "Continue", "turn-from-native"),
                        opening_context)
                    assert native_factory.native.sent[-1] == ("steer", "steer-op")
                    steer_ack = await http.publish_core_steer_receipt(
                        ticket.ticket, submit_frame=steer_frame,
                        core_receipt=steer_receipt,
                        context=opening_context, receipt_revision=1)
                    interrupt_receipt = await runtime.control(
                        ControlOperation(
                            "interrupt-op", "session", "interrupt",
                            expected_turn_id="turn-from-native",
                            reason="Requested by the agent"),
                        opening_context)
                    interrupt_ack = await http.publish_core_interrupt_receipt(
                        ticket.ticket, submit_frame=interrupt_frame,
                        core_receipt=interrupt_receipt,
                        context=opening_context, receipt_revision=1)
                    close_receipt = await runtime.close(
                        CloseOperation("close-op", "session",
                                       "Requested by the agent"),
                        opening_context)
                    close_ack = await http.publish_core_close_receipt(
                        ticket.ticket, submit_frame=close_frame,
                        core_receipt=close_receipt,
                        context=opening_context, receipt_revision=1)
                finally:
                    await runtime.shutdown(ShutdownPolicy(0, 0))
                    await journal.aclose()
                assert receipt_ack.operation_id == "op"
                assert steer_ack.operation_id == "steer-op"
                assert interrupt_ack.operation_id == "interrupt-op"
                assert close_ack.operation_id == "close-op"
                view = await http.get_operation(key, "op")
                assert view["executor_stage"] == core_receipt.stage
                assert view["intent_hash"] == submit_frame["intent_hash"]
                steer_view = await http.get_operation(key, "steer-op")
                assert steer_view["executor_stage"] == steer_receipt.stage
                assert steer_view["intent_hash"] == steer_frame["intent_hash"]
                for frame, receipt in ((interrupt_frame, interrupt_receipt),
                                       (close_frame, close_receipt)):
                    result = await http.get_operation(key, frame["operation_id"])
                    assert result["executor_stage"] == receipt.stage
                    assert result["intent_hash"] == frame["intent_hash"]
                return registered, snapshot

    registered, snapshot = asyncio.run(roundtrip())
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT publication_sequence,inventory_revision FROM "
            "execution_inventory_current WHERE server_id=? AND executor_id=?",
            (registered.server_id, registered.executor_id),
        ).fetchone()
    assert tuple(row) == (1, snapshot["inventory_revision"])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        receipt = uow.connection.execute(
            "SELECT stage FROM execution_receipts WHERE server_id=? AND executor_id=? "
            "AND operation_id='op' AND receipt_revision=1",
            (registered.server_id, registered.executor_id),
        ).fetchone()
    assert receipt["stage"] == "SUBMITTED"
    with deps.connection_factory.unit_of_work(write=False) as uow:
        steer_receipt = uow.connection.execute(
            "SELECT stage FROM execution_receipts WHERE server_id=? AND executor_id=? "
            "AND operation_id='steer-op' AND receipt_revision=1",
            (registered.server_id, registered.executor_id),
        ).fetchone()
    assert steer_receipt["stage"] == "SUBMITTED"
