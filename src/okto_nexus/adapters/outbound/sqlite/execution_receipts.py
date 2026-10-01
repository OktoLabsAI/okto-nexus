"""Durable R4 Core receipts for an already admitted operation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from nexus_connector_core import CoreError, decode_r4_frame, reduce_r4_receipt
from nexus_connector_core.protocol import canonical_json

from ....errors import ErrorCode, OktoNexusError
from .connection import ConnectionFactory
from .execution_tickets import VerifiedExecutionTicket


@dataclass(frozen=True, slots=True)
class AcceptedExecutionReceipt:
    operation_id: str
    receipt_revision: int
    stage: str
    reused: bool


@dataclass(frozen=True, slots=True)
class ExecutionOperationHistory:
    server_id: str
    executor_id: str
    operation_id: str
    binding_id: str
    session_id: str
    action: str
    intent_hash: str
    admission_state: str
    receipts: tuple[dict[str, Any], ...]
    subject_agent_id: str
    workspace_id: str
    actor_agent_id: str
    client_intent_id: str | None
    last_observed_at: str
    dispatch_state: str | None = None
    dispatch_error: dict | None = None
    execution_scope: dict | None = None

    def public_view(self) -> dict[str, Any]:
        latest = self.receipts[-1] if self.receipts else None
        return {
            "operation_id": self.operation_id,
            "client_intent_id": self.client_intent_id,
            "scope": self.execution_scope or {"server_id": self.server_id,
                      "executor_id": self.executor_id,
                      "binding_id": self.binding_id,
                      "agent_id": self.subject_agent_id,
                      "workspace_id": self.workspace_id,
                      "session_id": self.session_id},
            "action": self.action, "intent_hash": self.intent_hash,
            "admission_state": self.admission_state,
            "executor_stage": latest["stage"] if latest else None,
            "possible_effect": latest["possible_effect"] if latest else self.dispatch_state in {
                "SENDING", "DISPATCHED", "RECONCILING"},
            "retry_safe": latest["retry_safe"] if latest else False,
            "receipt_revision": latest["receipt_revision"] if latest else 0,
            "last_observed_at": self.last_observed_at,
            "error": ({"code": latest["error_code"], "stage": "executor",
                       "message": f"The executor reported {latest['error_code']}.",
                       "possible_effect": latest["possible_effect"], "retry_safe": latest["retry_safe"],
                       "operation_id": self.operation_id, "action": "Query this operation before requesting new work."}
                      if latest and latest.get("error_code") else self.dispatch_error if not latest else None),
            "follow_up_operation_ids": [],
        }


def read_execution_operation_history(factory: ConnectionFactory, *,
                                     server_id: str, executor_id: str | None,
                                     operation_id: str,
                                     subject_agent_id: str, actor_agent_id: str | None = None,
                                     ) -> ExecutionOperationHistory:
    """Read scoped subject/actor metadata and verified facts without a runtime."""
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        found = conn.execute(
            "SELECT executor_id,binding_id,subject_agent_id,actor_agent_id,"
            "workspace_id,session_id,action,intent_hash,admission_state,created_at,expected_revisions_json "
            "FROM execution_operations WHERE server_id=? AND operation_id=? "
            "AND (subject_agent_id=? OR actor_agent_id=?) AND (? IS NULL OR executor_id=?) LIMIT 2",
            (server_id, operation_id, subject_agent_id, actor_agent_id, executor_id, executor_id),
        ).fetchall()
        if not found:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                 "The operation was not found in this scope.", {})
        if len(found) != 1:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                 "The operation ID is ambiguous in this scope.", {})
        operation = found[0]
        executor_id = operation["executor_id"]
        rows = conn.execute(
            "SELECT canonical_frame,frame_digest,received_at FROM execution_receipts WHERE "
            "server_id=? AND executor_id=? AND operation_id=? "
            "ORDER BY receipt_revision",
            (server_id, executor_id, operation_id),
        ).fetchall()
        receipts: list[dict[str, Any]] = []
        projection = None
        try:
            for row in rows:
                raw = row["canonical_frame"]
                if raw is None or ("sha256:" + hashlib.sha256(
                        raw.encode("utf-8")).hexdigest()) != row["frame_digest"]:
                    raise ValueError("invalid stored receipt")
                parsed = decode_r4_frame(raw.encode("utf-8"))
                if (parsed["server_id"] != server_id or
                        parsed["executor_id"] != executor_id or
                        parsed["operation_id"] != operation_id or
                        parsed["agent_id"] != operation["subject_agent_id"] or
                        parsed["binding_id"] != operation["binding_id"] or
                        parsed["session_id"] != operation["session_id"] or
                        parsed["intent_hash"] != operation["intent_hash"]):
                    raise ValueError("stored receipt has a different operation")
                projection = reduce_r4_receipt(projection, parsed)
                receipts.append(parsed)
        except (CoreError, ValueError, TypeError) as exc:
            raise OktoNexusError(ErrorCode.DB_ERROR,
                                 "Stored operation receipt history is invalid.", {}) from exc
        intent_rows = conn.execute(
            "SELECT client_intent_id FROM execution_client_intents WHERE "
            "server_id=? AND actor_agent_id=? AND operation_id=? LIMIT 2",
            (server_id, operation["actor_agent_id"], operation_id),
        ).fetchall()
        if len(intent_rows) > 1:
            raise OktoNexusError(ErrorCode.DB_ERROR,
                                 "The operation has ambiguous intent provenance.", {})
        dispatch = conn.execute(
            "SELECT dispatch_state,last_error FROM execution_dispatch_outbox "
            "WHERE server_id=? AND executor_id=? AND operation_id=?",
            (server_id, executor_id, operation_id)).fetchone()
        return ExecutionOperationHistory(
            server_id, executor_id, operation_id, operation["binding_id"],
            operation["session_id"], operation["action"],
            operation["intent_hash"], operation["admission_state"],
            tuple(receipts),
            operation["subject_agent_id"], operation["workspace_id"],
            operation["actor_agent_id"],
            intent_rows[0]["client_intent_id"] if intent_rows else None,
            rows[-1]["received_at"] if rows else operation["created_at"],
            dispatch['dispatch_state'] if dispatch else None,
            json.loads(dispatch['last_error']) if dispatch and dispatch['last_error'] else None,
            json.loads(operation['expected_revisions_json']) or None,
        )


def append_execution_receipt(factory: ConnectionFactory, *,
                             principal: VerifiedExecutionTicket | None = None,
                             embedded_owner=None,
                             frame: Mapping[str, Any]) -> AcceptedExecutionReceipt:
    """Accept a Core fact only for the ticket's admitted operation.

    This never creates an operation or authorizes a native effect. Core owns
    the frame schema and ordered receipt reducer; SQLite owns durability.
    """
    if (principal is None) == (embedded_owner is None):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "One authenticated receipt owner is required.", {})
    if principal is not None and ("receipt:publish" not in principal.scopes or principal.binding_id is None):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                             "The ticket cannot publish operation receipts.", {})
    try:
        raw = canonical_json(dict(frame))
        parsed = decode_r4_frame(raw)
    except (CoreError, ValueError, TypeError, RecursionError) as exc:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                             "Invalid operation receipt frame.", {}) from exc
    if parsed["type"] != "operation.receipt":
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                             "An operation receipt frame is required.", {})
    if principal is not None and (parsed["server_id"] != principal.server_id or
            parsed["executor_id"] != principal.executor_id or
            parsed["binding_id"] != principal.binding_id or
            parsed["agent_id"] != principal.agent_id):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                             "The receipt is outside the ticket scope.", {})
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    key = (parsed["server_id"], parsed["executor_id"], parsed["operation_id"])
    with factory.unit_of_work() as uow:
        conn = uow.connection
        if embedded_owner is not None:
            owner = embedded_owner
            if ((parsed["server_id"], parsed["executor_id"]) !=
                    (owner.key.server_id, owner.key.executor_id)
                    or not owner.dispatcher.repo.owns(uow, owner_id=owner.dispatcher.owner_id,
                        epoch=owner.dispatcher.epoch, now=owner.deps.clock.now_iso())
                    or conn.execute("SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
                        "AND kind='embedded' AND owner_instance_id=? AND generation=? AND revoked_at IS NULL",
                        (owner.key.server_id,owner.key.executor_id,owner.dispatcher.owner_id,owner.generation)).fetchone() is None):
                raise OktoNexusError(ErrorCode.CONFLICT, "The embedded receipt owner changed.", {})
            # Current ownership authorizes persistence; the immutable binding
            # and dispatched lease below identify the historical native effect.
            from nexus_connector_core import validate_r4_receipt_binding
            publication = conn.execute("SELECT binding_json FROM execution_local_publications "
                "WHERE server_id=? AND executor_id=? AND operation_id=?", key).fetchone()
            try:
                binding = validate_r4_receipt_binding(json.loads(publication[0]))
                if any(parsed.get(name) != value for name, value in binding["source"].items()):
                    raise ValueError("The historical receipt source changed.")
            except (CoreError, ValueError, TypeError) as exc:
                raise OktoNexusError(ErrorCode.CONFLICT, "The embedded receipt binding is invalid.", {}) from exc
        operation = conn.execute(
            "SELECT binding_id,subject_agent_id,session_id,intent_hash,"
            "admission_state,action,expected_revisions_json FROM execution_operations WHERE server_id=? "
            "AND executor_id=? AND operation_id=?", key,
        ).fetchone()
        if operation is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                 "The admitted operation was not found.", {})
        if (operation["binding_id"] != parsed["binding_id"] or
                operation["subject_agent_id"] != parsed["agent_id"] or
                operation["session_id"] != parsed["session_id"] or
                operation["intent_hash"] != parsed["intent_hash"] or
                operation["admission_state"] not in {
                    "ACCEPTED", "DISPATCH_PENDING", "DISPATCHED",
                    "RECONCILING", "RESOLVED_TERMINAL",
                }):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                 "The receipt does not match an admitted operation.", {})
        # Canonical R4 admissions carry an immutable scope and a dispatched
        # lease. Historical rows remain readable without promoting a session.
        scope = json.loads(operation['expected_revisions_json'])
        if scope:
            dispatched = conn.execute(
                "SELECT l.scope_json,l.connection_id,l.connection_generation,l.applied_at "
                "FROM execution_dispatch_outbox o JOIN execution_leases l "
                "ON l.server_id=o.server_id AND l.executor_id=o.executor_id "
                "AND l.lease_id=o.lease_id AND l.lease_serial=o.lease_serial "
                "WHERE o.server_id=? AND o.executor_id=? AND o.operation_id=? "
                "AND o.dispatch_state IN ('SENDING','DISPATCHED','RECONCILING','RESOLVED_TERMINAL')",
                key).fetchone()
            if (dispatched is None or not dispatched['applied_at'] or
                    not dispatched['scope_json'] or json.loads(dispatched['scope_json']) != scope or
                    dispatched['connection_id'] != parsed['connection_id'] or
                    dispatched['connection_generation'] != parsed['connection_generation']):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                     "The receipt has no matching authorized dispatch.", {})
        existing = conn.execute(
            "SELECT frame_digest,stage FROM execution_receipts WHERE server_id=? "
            "AND executor_id=? AND operation_id=? AND receipt_revision=?",
            (*key, parsed["receipt_revision"]),
        ).fetchone()
        if existing is not None:
            if existing["frame_digest"] != digest:
                raise OktoNexusError(ErrorCode.CONFLICT,
                                     "A different receipt has this revision.", {})
            return AcceptedExecutionReceipt(parsed["operation_id"],
                                            parsed["receipt_revision"],
                                            existing["stage"], True)
        rows = conn.execute(
            "SELECT canonical_frame,frame_digest FROM execution_receipts WHERE server_id=? "
            "AND executor_id=? AND operation_id=? ORDER BY receipt_revision", key,
        ).fetchall()
        projection = None
        try:
            for row in rows:
                raw_previous = row["canonical_frame"]
                if (raw_previous is None or "sha256:" + hashlib.sha256(
                        raw_previous.encode("utf-8")).hexdigest() != row["frame_digest"]):
                    raise ValueError("missing receipt provenance")
                projection = reduce_r4_receipt(
                    projection, decode_r4_frame(raw_previous.encode("utf-8")))
            projection = reduce_r4_receipt(projection, parsed)
        except (CoreError, ValueError, TypeError) as exc:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                 "The receipt sequence or provenance is invalid.", {}) from exc
        conn.execute(
            "INSERT INTO execution_receipts(server_id,executor_id,operation_id,"
            "receipt_revision,intent_hash,stage,possible_effect,retry_safe,"
            "native_id,error_code,received_at,source_connection_id,"
            "source_connection_generation,frame_digest,canonical_frame) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?,?,?,?)",
            (*key, projection.receipt_revision, parsed["intent_hash"],
             projection.stage, int(projection.possible_effect),
             int(projection.retry_safe), projection.native_id,
             parsed.get("error_code"), projection.source_connection_id,
             projection.source_connection_generation, digest,
             raw.decode("utf-8")),
        )
        state = ("RECONCILING" if projection.stage == "OUTCOME_UNKNOWN" else
                 "RESOLVED_TERMINAL" if projection.stage in {
                     "SUCCEEDED", "FAILED", "CANCELLED"} else "DISPATCHED")
        conn.execute(
            "UPDATE execution_dispatch_outbox SET last_receipt_revision=?,"
            "dispatch_state=?,reservation_class=NULL,reserved_bytes=0,"
            "reserved_at=NULL "
            "WHERE server_id=? AND executor_id=? AND operation_id=?",
            (projection.receipt_revision, state, *key),
        )
        conn.execute(
            "UPDATE execution_operations SET admission_state=? WHERE "
            "server_id=? AND executor_id=? AND operation_id=?",
            (state, *key),
        )
        if (scope and operation['action'] == 'runtime.open' and
                projection.stage in ('SUBMITTED', 'SUCCEEDED') and projection.native_id):
            # Core open returns SUBMITTED only after registering its native
            # handle and starting the event pump. Preserve that receipt stage;
            # readiness is distinct from a successful turn or lease install.
            # A historical owner may publish its receipt but cannot make a
            # replaced executor ready. Reconciliation owns that transition.
            conn.execute(
                "UPDATE execution_sessions SET lifecycle_state='READY' "
                "WHERE server_id=? AND executor_id=? AND session_id=? "
                "AND open_operation_id=? AND owner_generation=? AND lifecycle_state='OPEN_PENDING' "
                "AND EXISTS (SELECT 1 FROM execution_executors e "
                "WHERE e.server_id=execution_sessions.server_id AND e.executor_id=execution_sessions.executor_id "
                "AND e.owner_instance_id=? AND e.generation=? AND e.revoked_at IS NULL "
                "AND e.control_state='CONTROL_READY')",
                (key[0], key[1], parsed['session_id'], key[2], scope['session_owner_generation'],
                 projection.source_connection_id, projection.source_connection_generation))
        if (scope and operation['action'] == 'runtime.close' and
                projection.stage in ('SUBMITTED', 'SUCCEEDED')):
            # A Core close receipt is submitted only after observed stop and
            # owned-slot release. Unknown or historical-owner receipts cannot
            # close the current session; preserve the original receipt stage.
            conn.execute(
                "UPDATE execution_sessions SET lifecycle_state='CLOSED',lease_state='CLOSED' "
                "WHERE server_id=? AND executor_id=? AND session_id=? "
                "AND owner_generation=? AND lifecycle_state='READY' "
                "AND EXISTS (SELECT 1 FROM execution_executors e "
                "WHERE e.server_id=execution_sessions.server_id AND e.executor_id=execution_sessions.executor_id "
                "AND e.owner_instance_id=? AND e.generation=? AND e.revoked_at IS NULL "
                "AND e.control_state='CONTROL_READY')",
                (key[0], key[1], parsed['session_id'], scope['session_owner_generation'],
                 projection.source_connection_id, projection.source_connection_generation))
    return AcceptedExecutionReceipt(parsed["operation_id"],
                                    projection.receipt_revision,
                                    projection.stage, False)
