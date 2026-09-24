"""Explicit operator recovery of existing attempts; never creates native work."""
import hashlib
import json

from ..domain.base import new_id
from ..errors import ErrorCode, OktoNexusError


def conflict(message):
    return OktoNexusError(ErrorCode.CONFLICT, message, {})


class RuntimeOperationMaintenanceService:
    def __init__(self, *, access, owner, inbox, handoffs=None):
        self.access, self.owner, self.inbox = access, owner, inbox
        self.handoffs = handoffs

    def run(self, context, *, action="inspect", operation_id=None, after_operation_id=None, limit=50,
            expected_state=None, expected_attempt_id=None, expected_owner_epoch=None,
            idempotency_key=None, reason=None, acknowledge_duplicate_risk=False,
            expected_handoff_id=None, expected_claim_epoch=None):
        self.access.authorize_maintenance(context)
        if action == "inspect":
            if any(value is not None for value in (expected_state, expected_attempt_id, expected_owner_epoch, idempotency_key, reason, expected_handoff_id, expected_claim_epoch)) or acknowledge_duplicate_risk:
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Inspection does not accept mutation fields.", {})
            return self._inspect(context, operation_id=operation_id, after_operation_id=after_operation_id, limit=limit)
        recover_work = action == "recover_handoff"
        if (not isinstance(action, str) or action not in {"cancel_pending", "release_to_inbox", "abandon_command", "recover_handoff"} or after_operation_id is not None or limit != 50
                or not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 128 or not isinstance(expected_state, str)
                or not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128
                or not isinstance(reason, str) or not 1 <= len(reason) <= 512 or not reason.strip()
                or type(acknowledge_duplicate_risk) is not bool
                or (expected_owner_epoch is not None and (type(expected_owner_epoch) is not int or expected_owner_epoch < 1))
                or (expected_attempt_id is not None and not isinstance(expected_attempt_id, str))):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Recovery requires an exact attempt snapshot, idempotency key and audit reason.", {})
        if recover_work:
            if (not isinstance(expected_handoff_id, str) or not 1 <= len(expected_handoff_id) <= 128
                    or type(expected_claim_epoch) is not int or expected_claim_epoch < 1):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Work recovery requires the exact handoff and claim generation.", {})
        elif expected_handoff_id is not None or expected_claim_epoch is not None:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Claim fields require recover_handoff.", {})
        owner = self.owner
        if not owner or owner._stop.is_set() or owner._quiescing.is_set():
            raise conflict("Recovery requires the active serve owner.")
        # This is an in-memory ownership check, not process polling. Unknown
        # attempts are never queued again, so an inactive one cannot restart.
        if action != "cancel_pending" and owner.operation_inflight(operation_id):
            raise conflict("An external call is still in flight; its timeout does not release ownership.")
        digest = hashlib.sha256(json.dumps([action, operation_id, expected_state, expected_attempt_id,
            expected_owner_epoch, reason, acknowledge_duplicate_risk] +
            ([expected_handoff_id, expected_claim_epoch] if recover_work else []), separators=(",", ":")).encode()).hexdigest()
        actor, now = context.actor_agent_id or "operator", self.access.clock.now_iso()
        with self.access.cf.unit_of_work() as uow:
            self.access.authorize_maintenance(context, uow=uow)
            if not owner.repo.owns(uow, owner_id=owner.owner_id, epoch=owner.epoch, now=now):
                raise conflict("Recovery owner changed.")
            existing = uow.connection.execute("SELECT request_hash,response FROM runtime_operation_reconciliations "
                "WHERE actor_agent_id=? AND idempotency_key=?", (actor, idempotency_key)).fetchone()
            if existing:
                if existing["request_hash"] != digest:
                    raise conflict("Recovery key already binds a different decision.")
                return json.loads(existing["response"])
            table = "delivery_outbox"
            row = uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None:
                table = "runtime_commands"
                row = uow.connection.execute("SELECT * FROM runtime_commands WHERE operation_id=?", (operation_id,)).fetchone()
            if (not row or row["reconciliation_id"] or row["status"] != expected_state or
                    row["attempt_id"] != expected_attempt_id or row["owner_epoch"] != expected_owner_epoch
                    or (row["terminal_event_id"] and not recover_work)):
                raise conflict("Operation changed, completed, or was already reconciled; refresh its snapshot.")
            binding = uow.connection.execute("SELECT handoff_id,claim_epoch FROM runtime_handoff_bindings WHERE operation_id=?", (operation_id,)).fetchone()
            if binding and not recover_work:
                raise conflict("Managed work requires canonical handoff recovery; its claim cannot be released as conversation.")
            if recover_work and (not self.handoffs or table != "delivery_outbox" or not binding
                    or binding["handoff_id"] != expected_handoff_id or binding["claim_epoch"] != expected_claim_epoch):
                raise conflict("Operation does not bind the expected canonical claim.")
            pending = action == "cancel_pending"
            if pending:
                if row["status"] not in {"PENDING", "CLAIMED"} or acknowledge_duplicate_risk:
                    raise conflict("Only an attempt before send-intent can be cancelled without uncertain effects.")
            else:
                eligible = {"OUTCOME_UNKNOWN", "SENT_UNCONFIRMED", "ACCEPTED"}
                if recover_work:
                    eligible |= {"REJECTED", "CANCELLED", "FAILED_FINAL"}
                if (not acknowledge_duplicate_risk or row["status"] not in eligible
                        or (not recover_work and (action == "release_to_inbox") != (table == "delivery_outbox"))):
                    raise conflict("Uncertain recovery requires explicit duplicate-risk acknowledgement and the correct source action.")
                if uow.connection.execute("SELECT 1 FROM harness_sessions WHERE endpoint_id=? AND lifecycle_state NOT IN "
                        "('stopped','detached','unknown','outcome_unknown','legacy_unlinked') LIMIT 1", (row["endpoint_id"],)).fetchone():
                    raise conflict("Close or reconcile the endpoint's runtime before takeover; stored readiness is not proof of stop.")
                if uow.connection.execute("SELECT 1 FROM runtime_open_requests WHERE endpoint_id=? AND status='RESERVED' LIMIT 1",
                                          (row["endpoint_id"],)).fetchone():
                    raise conflict("An endpoint start remains reserved.")
            rid = new_id("reconcile")
            response = {"reconciliation_id": rid, "operation_id": operation_id, "action": action,
                "transport_state": "CANCELLED" if pending else row["status"], "previous_transport_state": row["status"],
                "ack_level": row["ack_level"], "native_replayed": False, "result_invented": False,
                "duplicate_risk_acknowledged": not pending, "inbox_released": table == "delivery_outbox" and not recover_work,
                "endpoint_quarantined": not pending}
            if recover_work:
                response["handoff"] = self.handoffs.recover_runtime_claim(uow, context=context, operation=row,
                    handoff_id=expected_handoff_id, claim_epoch=expected_claim_epoch, reason=reason, reconciliation_id=rid)
            uow.connection.execute("INSERT INTO runtime_operation_reconciliations(reconciliation_id,operation_id,source_kind,actor_agent_id,"
                "idempotency_key,request_hash,action,previous_state,attempt_id,owner_epoch,endpoint_id,duplicate_risk_acknowledged,reason,response,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (rid, operation_id, table, actor, idempotency_key, digest,
                "abandon_command" if recover_work else action, row["status"],
                row["attempt_id"], row["owner_epoch"], row["endpoint_id"], int(not pending), reason, json.dumps(response, sort_keys=True), now))
            if recover_work:
                uow.connection.execute("UPDATE runtime_operation_reconciliations SET canonical_action='reopen_handoff',handoff_id=?,claim_epoch=? WHERE reconciliation_id=?",
                                       (expected_handoff_id, expected_claim_epoch, rid))
            uow.connection.execute(f"UPDATE {table} SET reconciliation_id=?,updated_at=?" +
                (",status='CANCELLED',reason='operator_cancelled_before_send'" if pending else "") + " WHERE operation_id=?", (rid, now, operation_id))
            if table == "delivery_outbox" and not recover_work:
                self.inbox.release_runtime_reservation(uow, operation_id=operation_id)
            if not pending:
                uow.connection.execute("UPDATE agent_endpoints SET health='quarantined',health_reason='operator_takeover',updated_at=? WHERE endpoint_id=?",
                                       (now, row["endpoint_id"]))
                self.access.endpoints.invalidate_configuration(uow, endpoint_ids=[row["endpoint_id"]], now=now)
        owner.wake()
        return response

    def _inspect(self, context, *, operation_id=None, after_operation_id=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100 or any(value is not None and (
                not isinstance(value, str) or not 1 <= len(value) <= 128) for value in (operation_id, after_operation_id)):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Operation inspection limit must be 1..100.", {})
        queries = []
        for table in ("delivery_outbox", "runtime_commands"):
            queries.append(f"SELECT o.operation_id,'{table}' AS source_kind,o.endpoint_id,e.agent_id,e.workspace_id,"
                "o.runtime_session_id,o.status AS state,o.reason,o.ack_level,o.attempt_id,o.owner_epoch,o.terminal_event_id,"
                "o.reconciliation_id,o.created_at,o.updated_at,s.lifecycle_state AS runtime_lifecycle "
                f"FROM {table} o JOIN agent_endpoints e ON e.endpoint_id=o.endpoint_id "
                "LEFT JOIN harness_sessions s ON s.session_id=o.runtime_session_id")
        query = "SELECT * FROM (" + " UNION ALL ".join(queries) + ") WHERE operation_id>?"
        values = [after_operation_id or ""]
        if operation_id:
            query += " AND operation_id=?"
            values.append(operation_id)
        with self.access.cf.unit_of_work(write=False) as uow:
            if not self.access.authenticate(context, uow=uow, require_feature=False):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Operation inspection requires the operator.", {})
            rows = uow.connection.execute(query + " ORDER BY operation_id LIMIT ?", (*values, limit + 1)).fetchall()
            items = []
            for row in rows[:limit]:
                item = dict(row)
                audit = uow.connection.execute("SELECT reconciliation_id,action,canonical_action,handoff_id,claim_epoch,previous_state,duplicate_risk_acknowledged,reason,created_at "
                    "FROM runtime_operation_reconciliations WHERE reconciliation_id=?", (row["reconciliation_id"],)).fetchone()
                item["reconciliation"] = dict(audit) if audit else None
                binding = uow.connection.execute("SELECT handoff_id,claim_epoch FROM runtime_handoff_bindings WHERE operation_id=?",
                                                 (row["operation_id"],)).fetchone()
                item["handoff"] = dict(binding) if binding else None
                items.append(item)
        return {"items": items, "has_more": len(rows) > limit,
                "next_operation_id": items[-1]["operation_id"] if len(rows) > limit else None}
