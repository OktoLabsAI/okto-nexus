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
                    or ((row["terminal_event_id"] or (table == 'delivery_outbox' and row['canonical_terminal_operation_id'])) and not recover_work)):
                raise conflict("Operation changed, completed, or was already reconciled; refresh its snapshot.")
            if table == 'delivery_outbox':
                self._require_canonical_recovery(uow, operation_id, action)
            binding = uow.connection.execute("SELECT handoff_id,claim_epoch FROM runtime_handoff_bindings WHERE operation_id=?", (operation_id,)).fetchone()
            if binding and not recover_work:
                raise conflict("Managed work requires canonical handoff recovery; its claim cannot be released as conversation.")
            if recover_work and (not self.handoffs or table != "delivery_outbox" or not binding
                    or binding["handoff_id"] != expected_handoff_id or binding["claim_epoch"] != expected_claim_epoch):
                raise conflict("Operation does not bind the expected canonical claim.")
            pending = action == "cancel_pending"
            # Only the owner's typed pre-write failure supplies this proof.
            # A generic rejection, exception message or NONE acknowledgement
            # alone is not evidence that an external call never wrote bytes.
            no_write_proof = (table == "delivery_outbox" and row["reason"] == "native_write_not_started"
                and row["ack_level"] == "NONE" and row["attempt_id"] is not None
                and row["native_thread_id"] is None and row["native_turn_id"] is None)
            if no_write_proof and (row['retry_basis'] == 'CORE_NO_EFFECT' or uow.connection.execute(
                    'SELECT 1 FROM execution_delivery_attempt_history WHERE domain_operation_id=?', (operation_id,)).fetchone()):
                # The display label cannot replace the correlated Core proof.
                no_write_proof = uow.connection.execute(
                    'SELECT 1 FROM execution_delivery_attempt_history h JOIN execution_receipts r '
                    'ON r.server_id=h.server_id AND r.executor_id=h.executor_id '
                    'AND r.operation_id=h.proof_operation_id AND r.receipt_revision=h.proof_receipt_revision '
                    "WHERE h.domain_operation_id=? AND h.proof_operation_id=? AND r.stage='FAILED' "
                    'AND r.possible_effect=0 AND r.retry_safe=1', (operation_id, row['attempt_id'])).fetchone() is not None
            not_sent = action == "release_to_inbox" and row["status"] == "REJECTED" and no_write_proof
            safe_wait = row["status"] == "RETRY_WAIT" and no_write_proof and row["retry_basis"] in {"LANE_BUSY_BEFORE_WRITE", "APPROVED_ENDPOINT_BEFORE_WRITE", "CORE_NO_EFFECT"}
            if pending:
                if (row["status"] not in {"PENDING", "CLAIMED"} and not safe_wait) or acknowledge_duplicate_risk:
                    raise conflict("Cancellation requires an attempt before send-intent or a proven-safe retry wait.")
            elif not_sent:
                if acknowledge_duplicate_risk:
                    raise conflict("A proven pre-write rejection requires no duplicate-risk acknowledgement.")
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
                "duplicate_risk_acknowledged": not pending and not not_sent, "inbox_released": table == "delivery_outbox" and not recover_work,
                "endpoint_quarantined": not pending and not not_sent}
            if recover_work:
                response["handoff"] = self.handoffs.recover_runtime_claim(uow, context=context, operation=row,
                    handoff_id=expected_handoff_id, claim_epoch=expected_claim_epoch, reason=reason, reconciliation_id=rid)
            uow.connection.execute("INSERT INTO runtime_operation_reconciliations(reconciliation_id,operation_id,source_kind,actor_agent_id,"
                "idempotency_key,request_hash,action,previous_state,attempt_id,owner_epoch,endpoint_id,duplicate_risk_acknowledged,reason,response,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (rid, operation_id, table, actor, idempotency_key, digest,
                "abandon_command" if recover_work else action, row["status"],
                row["attempt_id"], row["owner_epoch"], row["endpoint_id"], int(not pending and not not_sent), reason, json.dumps(response, sort_keys=True), now))
            if recover_work:
                uow.connection.execute("UPDATE runtime_operation_reconciliations SET canonical_action='reopen_handoff',handoff_id=?,claim_epoch=? WHERE reconciliation_id=?",
                                       (expected_handoff_id, expected_claim_epoch, rid))
            uow.connection.execute(f"UPDATE {table} SET reconciliation_id=?,updated_at=?" +
                (",status='CANCELLED',reason='operator_cancelled_before_send'" if pending else "") + " WHERE operation_id=?", (rid, now, operation_id))
            if table == "delivery_outbox" and not recover_work:
                self.inbox.release_runtime_reservation(uow, operation_id=operation_id)
                if pending:
                    self._cancel_canonical_pending(uow, operation_id)
            if not pending and not not_sent:
                uow.connection.execute("UPDATE agent_endpoints SET health='quarantined',health_reason='operator_takeover',updated_at=? WHERE endpoint_id=?",
                                       (now, row["endpoint_id"]))
                self.access.endpoints.invalidate_configuration(uow, endpoint_ids=[row["endpoint_id"]], now=now)
        owner.wake()
        return response

    @staticmethod
    def _cancel_canonical_pending(uow, operation_id):
        # The reconciliation marker, inbox release and capacity release share
        # the writer transaction. A reserved sender must still cross its CAS
        # fence, so it cannot send after this cancellation commits.
        conn = uow.connection
        rows = conn.execute(
            'SELECT p.server_id,p.executor_id,p.operation_id,p.admission_state,x.dispatch_state '
            'FROM execution_domain_deliveries m JOIN execution_operations p '
            'USING(server_id,executor_id,operation_id) LEFT JOIN execution_dispatch_outbox x '
            'USING(server_id,executor_id,operation_id) WHERE m.domain_operation_id=?',
            (operation_id,)).fetchall()
        for row in rows:
            if (row['dispatch_state'] not in (None, 'PENDING', 'RESERVED') or
                    row['admission_state'] not in ('ACCEPTED', 'DISPATCH_PENDING')):
                raise conflict('Canonical dispatch crossed its send fence; pending cancellation is unavailable.')
            key = (row['server_id'], row['executor_id'], row['operation_id'])
            error = json.dumps(dict(code='OPERATOR_CANCELLED', stage='dispatch',
                message='Cancelled before native dispatch.', possible_effect=False,
                retry_safe=False, operation_id=row['operation_id']))
            conn.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,last_error) "
                "VALUES(?,?,?,'RESOLVED_TERMINAL',?) ON CONFLICT(server_id,executor_id,operation_id) DO UPDATE SET "
                "dispatch_state='RESOLVED_TERMINAL',last_error=excluded.last_error,"
                "reservation_class=NULL,reserved_bytes=0,reserved_at=NULL", (*key, error))
            conn.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' "
                "WHERE server_id=? AND executor_id=? AND operation_id=?", key)
            conn.execute("UPDATE execution_sessions SET lifecycle_state='FAILED' WHERE server_id=? AND executor_id=? "
                "AND open_operation_id=? AND lifecycle_state='OPEN_PENDING' AND lease_state='NONE'", key)

    @staticmethod
    def _require_canonical_recovery(uow, operation_id, action):
        rows = uow.connection.execute(
            'SELECT x.dispatch_state,s.lifecycle_state,s.lease_state FROM execution_domain_deliveries m '
            'JOIN execution_operations p USING(server_id,executor_id,operation_id) '
            'JOIN execution_dispatch_outbox x USING(server_id,executor_id,operation_id) '
            'JOIN execution_sessions s ON s.server_id=p.server_id AND s.executor_id=p.executor_id AND s.session_id=p.session_id '
            'WHERE m.domain_operation_id=?', (operation_id,)).fetchall()
        if not rows:
            return
        # This check shares the writer transaction with the reconciliation marker.
        # begin_execution_send revalidates that marker before crossing its fence.
        if action == 'cancel_pending':
            if any(r['dispatch_state'] not in ('PENDING', 'RESERVED') for r in rows):
                raise conflict('Canonical dispatch crossed its send fence; pending cancellation is unavailable.')
        elif any(r['lifecycle_state'] != 'CLOSED' or r['lease_state'] != 'CLOSED' for r in rows):
            raise conflict('Close and reconcile the canonical session before recovering its domain claim.')

    def _inspect(self, context, *, operation_id=None, after_operation_id=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100 or any(value is not None and (
                not isinstance(value, str) or not 1 <= len(value) <= 128) for value in (operation_id, after_operation_id)):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Operation inspection limit must be 1..100.", {})
        queries = []
        for table in ("delivery_outbox", "runtime_commands"):
            queries.append(f"SELECT o.operation_id,'{table}' AS source_kind,o.endpoint_id,e.agent_id,e.workspace_id,"
                "o.runtime_session_id,o.status AS state,o.reason,o.ack_level,o.attempt_id,o.owner_epoch,o.terminal_event_id,"
                "o.reconciliation_id,o.created_at,o.updated_at,s.lifecycle_state AS runtime_lifecycle," +
                ("o.next_attempt_at,o.retry_basis,o.admission_binding,o.next_binding " if table == "delivery_outbox" else
                 "NULL AS next_attempt_at,NULL AS retry_basis,NULL AS admission_binding,NULL AS next_binding ") +
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
                for field in ("admission_binding", "next_binding"):
                    item[field] = json.loads(item[field]) if item[field] else None
                audit = uow.connection.execute("SELECT reconciliation_id,action,canonical_action,handoff_id,claim_epoch,previous_state,duplicate_risk_acknowledged,reason,created_at "
                    "FROM runtime_operation_reconciliations WHERE reconciliation_id=?", (row["reconciliation_id"],)).fetchone()
                item["reconciliation"] = dict(audit) if audit else None
                binding = uow.connection.execute("SELECT handoff_id,claim_epoch FROM runtime_handoff_bindings WHERE operation_id=?",
                                                 (row["operation_id"],)).fetchone()
                item["handoff"] = dict(binding) if binding else None
                if operation_id and row["source_kind"] == "delivery_outbox":
                    item['canonical_attempt_history'] = [dict(r) for r in uow.connection.execute(
                        'SELECT operation_id,server_id,executor_id,endpoint_id,attempt_number,'
                        'proof_operation_id,proof_receipt_revision,archived_at FROM execution_delivery_attempt_history '
                        'WHERE domain_operation_id=? ORDER BY attempt_number,operation_id LIMIT 6', (operation_id,))]
                    item['canonical_operations'] = [dict(r) for r in uow.connection.execute(
                        'SELECT p.server_id,p.executor_id,p.operation_id,p.session_id,p.action,x.dispatch_state,'
                        's.lifecycle_state,s.lease_state FROM execution_domain_deliveries m '
                        'JOIN execution_operations p USING(server_id,executor_id,operation_id) '
                        'JOIN execution_dispatch_outbox x USING(server_id,executor_id,operation_id) '
                        'JOIN execution_sessions s ON s.server_id=p.server_id AND s.executor_id=p.executor_id AND s.session_id=p.session_id '
                        'WHERE m.domain_operation_id=? ORDER BY p.operation_id LIMIT 3', (operation_id,))]
                    # Detail-only, bounded history. No payload, credential or
                    # new delivery authority is reconstructed from observations.
                    history = uow.connection.execute(
                        "SELECT sequence,attempt_id,owner_epoch,endpoint_id,runtime_session_id,state,"
                        "ack_level,reason,native_thread_id,native_turn_id,terminal_event_id,occurred_at,provenance,next_attempt_at,retry_basis,"
                        "admission_binding,next_binding,endpoint_revision,profile_revision "
                        "FROM runtime_delivery_attempt_events WHERE operation_id=? ORDER BY sequence DESC LIMIT 65",
                        (operation_id,)).fetchall()
                    item["attempt_history"] = [dict(event) for event in reversed(history[:64])]
                    for event in item["attempt_history"]:
                        for field in ("admission_binding", "next_binding"):
                            event[field] = json.loads(event[field]) if event[field] else None
                    item["attempt_history_truncated"] = len(history) > 64
                items.append(item)
        return {"items": items, "has_more": len(rows) > limit,
                "next_operation_id": items[-1]["operation_id"] if len(rows) > limit else None}
