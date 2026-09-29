"""Durable, effect-free R4 intent resolution for a canonical agent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from typing import Any, Mapping

from nexus_connector_core import r4_submit_intent_hash
from nexus_connector_core.protocol import canonical_json

from ..errors import ErrorCode, OktoNexusError
from ..adapters.outbound.sqlite.connection import ConnectionFactory
from ..adapters.outbound.sqlite.execution_agent_revisions import (
    current_agent_revisions,
)
from .execution_binding_proposals import _agent_guard


_INTENTS = {"runtime.start": "runtime.open", "turn.submit": "turn.submit"}


def resolve_execution_intent(
    factory: ConnectionFactory, *, actor_agent_id: str,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Store a stable resolution; never write an effect outbox or call Core."""
    required = {"client_intent_id", "intent", "binding_id",
                "workspace_binding_id"}
    allowed = required | {"session_id", "new_session", "text", "target"}
    if (not isinstance(request, Mapping) or not required <= set(request) or
            not set(request) <= allowed or
            any(type(request[name]) is not str or
                not 1 <= len(request[name]) <= 160 for name in required) or
            request["intent"] not in _INTENTS):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid execution intent.", {})
    if ("new_session" in request and type(request["new_session"]) is not bool):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid session selection.", {})
    if (request["intent"] == "runtime.start" and
            (request.get("session_id") is not None or
             request.get("text") is not None or
             request.get("new_session") is not True)):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "An explicit new session is required to start.", {})
    if request["intent"] == "turn.submit" and (
            type(request.get("session_id")) is not str or
            not 1 <= len(request["session_id"]) <= 160 or
            type(request.get("text")) is not str or
            len(request["text"]) > 65536 or
            request.get("new_session") is True):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "A session and turn text are required.", {})
    target = request.get("target") or {"kind": "none", "expected_turn_id": None}
    if (not isinstance(target, Mapping) or
            set(target) != {"kind", "expected_turn_id"} or
            target["kind"] not in {"none", "native_turn_id", "current_run"} or
            (target["expected_turn_id"] is not None and
             (type(target["expected_turn_id"]) is not str or
              not 1 <= len(target["expected_turn_id"]) <= 160)) or
            (target["kind"] == "native_turn_id") !=
            (target["expected_turn_id"] is not None)):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid native turn target.", {})
    if target["kind"] != "none":
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "This intent cannot target an existing turn.", {})
    server_id, revisions, _ = current_agent_revisions(
        factory, agent_id=actor_agent_id)
    body_hash = "sha256:" + hashlib.sha256(canonical_json(dict(request))).hexdigest()
    with factory.unit_of_work() as uow:
        conn = uow.connection
        prior = conn.execute(
            "SELECT body_hash,resolved_json FROM execution_client_intents "
            "WHERE server_id=? AND actor_agent_id=? AND client_intent_id=?",
            (server_id, actor_agent_id, request["client_intent_id"]),
        ).fetchone()
        if prior is not None:
            if prior["body_hash"] != body_hash:
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The client intent ID has different content.", {})
            return json.loads(prior["resolved_json"])
        binding = conn.execute(
            "SELECT b.*,ep.agent_id,ep.adapter_id,ep.profile_id,"
            "w.workspace_id,w.status AS workspace_status,"
            "r.status AS realization_status FROM execution_bindings b "
            "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
            "JOIN execution_workspace_bindings w ON w.server_id=b.server_id "
            "AND w.executor_id=b.executor_id AND "
            "w.workspace_binding_id=b.workspace_binding_id "
            "JOIN execution_realizations r ON r.server_id=b.server_id "
            "AND r.executor_id=b.executor_id AND r.realization_ref=b.realization_ref "
            "WHERE b.server_id=? AND b.binding_id=? AND ep.agent_id=?",
            (server_id, request["binding_id"], actor_agent_id),
        ).fetchone()
        if (binding is None or
                binding["workspace_binding_id"] != request["workspace_binding_id"]):
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                  "The binding was not found in this agent scope.", {})
        action = _INTENTS[request["intent"]]
        blockers = ["remote_execution_unavailable"]
        if (binding["workspace_status"] != "READY" or
                binding["realization_status"] != "READY"):
            blockers.append("realization_not_ready")
        session_id = ("ses_" + secrets.token_hex(16)
                      if action == "runtime.open" else request["session_id"])
        owner_generation = 1
        if action == "turn.submit":
            session = conn.execute(
                "SELECT binding_id,workspace_id,workspace_binding_id,"
                "owner_generation,lifecycle_state FROM execution_sessions "
                "WHERE server_id=? AND executor_id=? AND session_id=?",
                (server_id, binding["executor_id"], session_id),
            ).fetchone()
            if (session is None or session["binding_id"] != request["binding_id"] or
                    session["workspace_id"] != binding["workspace_id"] or
                    session["workspace_binding_id"] !=
                    binding["workspace_binding_id"] or
                    session["lifecycle_state"] != "READY"):
                blockers.append("session_not_ready")
            else:
                owner_generation = session["owner_generation"]
        scope = {
            "server_id": server_id, "executor_id": binding["executor_id"],
            "binding_id": binding["binding_id"],
            "agent_id": actor_agent_id,
            "workspace_id": binding["workspace_id"],
            "workspace_binding_id": binding["workspace_binding_id"],
            "session_id": session_id,
            "session_owner_generation": owner_generation,
            "authorization_revision": revisions.authorization,
            "configuration_revision": revisions.configuration,
            "binding_revision": binding["binding_revision"],
            "credential_epoch": revisions.credential_epoch,
        }
        payload = (
            {"adapter_id": binding["adapter_id"],
             "candidate_ref": binding["candidate_ref"],
             "inventory_revision": binding["inventory_revision"],
             "realization_ref": binding["realization_ref"],
             "realization_revision": binding["realization_revision"],
             "profile_revision": 1, "mode": "managed"}
            if action == "runtime.open" else {"text": request["text"]}
        )
        if action == "runtime.open" and binding["profile_id"] is None:
            blockers.append("profile_unresolved")
        semantic = {
            **{name: scope[name] for name in (
                "server_id", "executor_id", "binding_id", "agent_id",
                "workspace_id", "workspace_binding_id", "session_id",
                "configuration_revision")},
            "action": action, "target": dict(target), "payload": payload,
        }
        operation_id = "op_" + secrets.token_hex(16)
        intent_id = "r4intent_" + secrets.token_hex(16)
        resolved = {
            "client_intent_id": request["client_intent_id"],
            "intent_id": intent_id, "operation_id": operation_id,
            "session_id": session_id, "reuse": False,
            "scope": scope, "semantic_intent": semantic,
            "intent_hash": r4_submit_intent_hash(semantic),
            "resolution_revision": 1,
            "expires_at": (datetime.now(timezone.utc) +
                           timedelta(minutes=10)).isoformat(),
            "can_submit": False, "blockers": blockers,
            "dispatch_owner": "server",
        }
        conn.execute(
            "INSERT INTO execution_client_intents(server_id,actor_agent_id,"
            "client_intent_id,body_hash,intent_id,operation_id,"
            "resolution_revision,resolved_json,created_at,source_guard_digest) "
            "VALUES (?,?,?,?,?,?,1,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?)",
            (server_id, actor_agent_id, request["client_intent_id"],
             body_hash, intent_id, operation_id,
             canonical_json(resolved).decode("utf-8"),
             _agent_guard(conn, actor_agent_id)),
        )
        return resolved


def read_execution_intent(factory: ConnectionFactory, *, actor_agent_id: str,
                          client_intent_id: str) -> dict[str, Any]:
    """Recover the original resolution; never resolve a missing intent."""
    if not isinstance(client_intent_id, str) or not 1 <= len(client_intent_id) <= 160:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid client intent ID.", {})
    server_id, _, _ = current_agent_revisions(factory, agent_id=actor_agent_id)
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT resolved_json FROM execution_client_intents WHERE "
            "server_id=? AND actor_agent_id=? AND client_intent_id=? "
            "AND intent_id GLOB 'r4intent_*'",
            (server_id, actor_agent_id, client_intent_id),
        ).fetchone()
    if row is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND,
                              "The client intent was not found.", {})
    resolution = json.loads(row["resolved_json"])
    from ..adapters.outbound.sqlite.execution_receipts import (
        read_execution_operation_history,
    )
    try:
        operation = read_execution_operation_history(
            factory, server_id=server_id,
            executor_id=resolution["scope"]["executor_id"],
            operation_id=resolution["operation_id"],
            subject_agent_id=actor_agent_id,
        ).public_view()
    except OktoNexusError as exc:
        if exc.code != ErrorCode.NOT_FOUND:
            raise
        operation = None
    return {"resolution": resolution, "operation": operation}
