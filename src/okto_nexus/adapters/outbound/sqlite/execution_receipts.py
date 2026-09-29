"""Durable R4 Core receipts for an already admitted operation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
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


def append_execution_receipt(factory: ConnectionFactory, *,
                             principal: VerifiedExecutionTicket,
                             frame: Mapping[str, Any]) -> AcceptedExecutionReceipt:
    """Accept a Core fact only for the ticket's admitted operation.

    This never creates an operation or authorizes a native effect. Core owns
    the frame schema and ordered receipt reducer; SQLite owns durability.
    """
    if "receipt:publish" not in principal.scopes or principal.binding_id is None:
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
    if (parsed["server_id"] != principal.server_id or
            parsed["executor_id"] != principal.executor_id or
            parsed["binding_id"] != principal.binding_id or
            parsed["agent_id"] != principal.agent_id):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                             "The receipt is outside the ticket scope.", {})
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    key = (parsed["server_id"], parsed["executor_id"], parsed["operation_id"])
    with factory.unit_of_work() as uow:
        conn = uow.connection
        operation = conn.execute(
            "SELECT binding_id,subject_agent_id,session_id,intent_hash,"
            "admission_state FROM execution_operations WHERE server_id=? "
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
            "SELECT canonical_frame FROM execution_receipts WHERE server_id=? "
            "AND executor_id=? AND operation_id=? ORDER BY receipt_revision", key,
        ).fetchall()
        projection = None
        try:
            for row in rows:
                if row["canonical_frame"] is None:
                    raise ValueError("missing receipt provenance")
                projection = reduce_r4_receipt(
                    projection, decode_r4_frame(row["canonical_frame"].encode("utf-8")))
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
        conn.execute(
            "UPDATE execution_dispatch_outbox SET last_receipt_revision=? "
            "WHERE server_id=? AND executor_id=? AND operation_id=?",
            (projection.receipt_revision, *key),
        )
    return AcceptedExecutionReceipt(parsed["operation_id"],
                                    projection.receipt_revision,
                                    projection.stage, False)
