"""Transport intents refer to existing inbox deliveries, never independent work."""
import json

from ....errors import ErrorCode, OktoNexusError


class SqliteRuntimeOutboxRepo:
    def has_history(self, uow):
        return uow.connection.execute("SELECT 1 FROM harness_sessions UNION ALL SELECT 1 FROM delivery_outbox "
            "UNION ALL SELECT 1 FROM runtime_commands UNION ALL SELECT 1 FROM runtime_open_requests LIMIT 1").fetchone() is not None

    def live_sessions(self, uow, *, endpoint_id):
        return [dict(row) for row in uow.connection.execute(
            "SELECT session_id FROM harness_sessions WHERE endpoint_id=? AND lifecycle_state='protocol_ready' "
            "AND owner_epoch=(SELECT epoch FROM runtime_dispatcher_owner WHERE owner_key='dispatcher') ORDER BY started_at,session_id",
            (endpoint_id,))]

    def enqueue(self, uow, *, envelope, context, endpoint, profile, session_id, now, authorization_revision):
        existing = uow.connection.execute("SELECT request_hash FROM delivery_outbox WHERE operation_id=?",
                                          (envelope.operation_id,)).fetchone()
        if existing:
            if existing[0] != envelope.request_hash():
                raise OktoNexusError(ErrorCode.CONFLICT, "Operation identity already binds different content.", {})
            return
        claimed = uow.connection.execute(
            "UPDATE message_deliveries SET consumer_kind='push',consumer_operation_id=? "
            "WHERE delivery_id=? AND status='unread' AND consumer_kind IS NULL",
            (envelope.operation_id, envelope.delivery_id))
        if claimed.rowcount != 1:
            raise OktoNexusError(ErrorCode.CONFLICT, "Logical delivery already has an executor.", {})
        uow.connection.execute(
            "INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,"
            "recipient_agent_id,endpoint_id,endpoint_revision,profile_revision,runtime_session_id,envelope,request_hash,"
            "root_operation_id,created_at,updated_at,authorization_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (envelope.operation_id, envelope.delivery_id, envelope.message_id, envelope.workspace_id,
             context.actor_agent_id, context.credential_binding, envelope.recipient_agent_id, endpoint["endpoint_id"],
             endpoint["revision"], profile["revision"] if profile else None, session_id, envelope.canonical_json(),
             envelope.request_hash(), envelope.root_operation_id, now, now, authorization_revision))

    def pending(self, uow, *, limit=32):
        return [dict(row) for row in uow.connection.execute(
            "SELECT pending.* FROM delivery_outbox pending WHERE pending.status='PENDING' AND NOT EXISTS "
            "(SELECT 1 FROM delivery_outbox busy WHERE busy.endpoint_id=pending.endpoint_id AND busy.reconciliation_id IS NULL AND "
            "(busy.status IN ('CLAIMED','SENDING','OUTCOME_UNKNOWN') OR "
            "(busy.status IN ('SENT_UNCONFIRMED','ACCEPTED') AND busy.terminal_event_id IS NULL))) "
            "AND NOT EXISTS (SELECT 1 FROM runtime_commands c WHERE c.endpoint_id=pending.endpoint_id AND c.reconciliation_id IS NULL AND "
            "(c.status IN ('CLAIMED','SENDING','OUTCOME_UNKNOWN') OR "
            "(c.starts_turn=1 AND c.status IN ('SENT_UNCONFIRMED','ACCEPTED') AND c.terminal_event_id IS NULL) OR "
            "(c.status='PENDING' AND (c.verb<>'send_turn' OR (c.created_at,c.operation_id)<(pending.created_at,pending.operation_id))))) "
            "ORDER BY pending.created_at,pending.operation_id LIMIT ?", (limit,))]

    def get(self, uow, operation_id):
        row = uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?", (operation_id,)).fetchone()
        return dict(row) if row else None

    def acquire_owner(self, uow, *, owner_id, now, lease_expires_at):
        contract = uow.connection.execute("SELECT required_contract FROM runtime_writer_contract WHERE singleton=1").fetchone()
        if not contract or contract[0] > 1:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR,
                "runtime_writer_incompatible: this package cannot own the store's writer contract.", {})
        row = uow.connection.execute("SELECT * FROM runtime_dispatcher_owner WHERE owner_key='dispatcher'").fetchone()
        if row and row["lease_expires_at"] > now and row["owner_id"] != owner_id:
            return None
        epoch = row["epoch"] + 1 if row else 1
        uow.connection.execute("UPDATE runtime_writer_contract SET required_contract=1, "
            "admission_enabled=EXISTS(SELECT 1 FROM pragma_function_list "
            "WHERE name='nexus_runtime_admission_on' AND builtin=0 AND narg=0), owner_id=?,owner_epoch=? "
            "WHERE singleton=1", (owner_id, epoch))
        uow.connection.execute(
            "INSERT INTO runtime_dispatcher_owner(owner_key,epoch,owner_id,lease_expires_at) VALUES('dispatcher',?,?,?) "
            "ON CONFLICT(owner_key) DO UPDATE SET epoch=excluded.epoch,owner_id=excluded.owner_id,lease_expires_at=excluded.lease_expires_at,"
            "recovery_store_id=NULL,recovery_watermark=NULL",
            (epoch, owner_id, lease_expires_at))
        # A previous external call might still finish. Never retry SENDING.
        uow.connection.execute("UPDATE delivery_outbox SET status='OUTCOME_UNKNOWN',reason='owner_lost',updated_at=? "
            "WHERE status IN ('SENDING','SENT_UNCONFIRMED','ACCEPTED') AND terminal_event_id IS NULL", (now,))
        uow.connection.execute("UPDATE delivery_outbox SET status='PENDING',owner_epoch=NULL,attempt_id=NULL,updated_at=? WHERE status='CLAIMED'", (now,))
        uow.connection.execute("UPDATE runtime_commands SET status='OUTCOME_UNKNOWN',reason='owner_lost',updated_at=? "
            "WHERE status IN ('SENDING','SENT_UNCONFIRMED','ACCEPTED') AND terminal_event_id IS NULL", (now,))
        uow.connection.execute("UPDATE runtime_commands SET status='CANCELLED',reason='session_owner_lost_before_send',updated_at=? "
            "WHERE status IN ('PENDING','CLAIMED') AND expected_owner_epoch<>?", (now, epoch))
        return epoch

    def set_recovery_boundary(self, uow, *, owner_id, epoch, store_id, watermark, now):
        return uow.connection.execute(
            "UPDATE runtime_dispatcher_owner SET recovery_store_id=?,recovery_watermark=? "
            "WHERE owner_key='dispatcher' AND owner_id=? AND epoch=? AND lease_expires_at>? "
            "AND recovery_watermark IS NULL", (store_id, watermark, owner_id, epoch, now)).rowcount == 1

    def finish_recovery(self, uow, *, epoch, now):
        # Captured acceptance alone is not a live connection or finished result.
        # Preserve its native identifiers for explicit reconciliation, not retry.
        uow.connection.execute("UPDATE delivery_outbox SET status='OUTCOME_UNKNOWN',reason='owner_lost',updated_at=? "
            "WHERE owner_epoch<>? AND terminal_event_id IS NULL AND status IN ('SENDING','SENT_UNCONFIRMED','ACCEPTED')",
            (now, epoch))
        uow.connection.execute("UPDATE runtime_commands SET status='OUTCOME_UNKNOWN',reason='owner_lost',updated_at=? "
            "WHERE owner_epoch<>? AND terminal_event_id IS NULL AND status IN ('SENDING','SENT_UNCONFIRMED','ACCEPTED')", (now, epoch))
        # Readiness is scoped to its process owner. Closing canonical presence
        # means loss of this connection only, never proof of native process exit.
        stale = "(owner_epoch IS NULL OR owner_epoch<>?) AND lifecycle_state IN ('protocol_ready','stop_requested','tracked','legacy_unlinked') AND status IN ('STARTING','RUNNING','INTERRUPTING','ERRORED')"
        uow.connection.execute("UPDATE agent_endpoints SET health='quarantined',health_reason='owner_lost',updated_at=? "
            "WHERE endpoint_id IN (SELECT endpoint_id FROM harness_sessions WHERE " + stale + ") "
            "OR endpoint_id IN (SELECT endpoint_id FROM runtime_open_requests WHERE status='RESERVED' "
            "AND (owner_epoch IS NULL OR owner_epoch<>?))", (now, epoch, epoch))
        uow.connection.execute("UPDATE sessions SET status='closed',closed_at=? WHERE status<>'closed' "
            "AND session_id IN (SELECT presence_session_id FROM harness_sessions WHERE " + stale + ")", (now, epoch))
        uow.connection.execute("UPDATE harness_sessions SET lifecycle_state='unknown',status='ERRORED',updated_at=? WHERE " + stale, (now, epoch))
        uow.connection.execute("UPDATE runtime_open_requests SET status='OUTCOME_UNKNOWN' WHERE status='RESERVED' "
            "AND (owner_epoch IS NULL OR owner_epoch<>?)", (epoch,))

    def heartbeat_owner(self, uow, *, owner_id, epoch, lease_expires_at, now):
        return uow.connection.execute(
            "UPDATE runtime_dispatcher_owner SET lease_expires_at=? WHERE owner_key='dispatcher' AND owner_id=? AND epoch=? AND lease_expires_at>?",
            (lease_expires_at, owner_id, epoch, now)).rowcount == 1

    def owns(self, uow, *, owner_id, epoch, now):
        return uow.connection.execute(
            "SELECT 1 FROM runtime_dispatcher_owner WHERE owner_key='dispatcher' AND owner_id=? AND epoch=? AND lease_expires_at>?",
            (owner_id, epoch, now)).fetchone() is not None

    def release_owner(self, uow, *, owner_id, epoch, now):
        uow.connection.execute(
            "UPDATE runtime_dispatcher_owner SET lease_expires_at=? WHERE owner_key='dispatcher' AND owner_id=? AND epoch=?",
            (now, owner_id, epoch))

    def claim(self, uow, *, operation_id, epoch, attempt_id, lease_expires_at, now):
        changed = uow.connection.execute(
            "UPDATE delivery_outbox SET status='CLAIMED',attempt_count=attempt_count+1,owner_epoch=?,attempt_id=?,lease_expires_at=?,updated_at=? "
            "WHERE operation_id=? AND status='PENDING'", (epoch, attempt_id, lease_expires_at, now, operation_id))
        return changed.rowcount == 1

    def bind_runtime(self, uow, *, operation_id, session_id, epoch, attempt_id):
        return uow.connection.execute("UPDATE delivery_outbox SET runtime_session_id=? WHERE operation_id=? "
            "AND status='SENDING' AND owner_epoch=? AND attempt_id=?",
            (session_id, operation_id, epoch, attempt_id)).rowcount == 1

    def observe(self, uow, *, operation_id, epoch, attempt_id, expected, status, now, reason=None, ack_level="NONE"):
        changed = uow.connection.execute(
            "UPDATE delivery_outbox SET status=?,reason=?,ack_level=?,updated_at=? WHERE operation_id=? "
            "AND owner_epoch=? AND attempt_id=? AND status=?", (status, reason, ack_level, now, operation_id, epoch, attempt_id, expected))
        if changed.rowcount == 1 and expected == "CLAIMED" and status in {"REJECTED", "CANCELLED"}:
            uow.connection.execute("UPDATE message_deliveries SET consumer_kind=NULL,consumer_operation_id=NULL "
                                   "WHERE consumer_operation_id=? AND consumer_kind='push'", (operation_id,))
        return changed.rowcount == 1

    @staticmethod
    def decode(row):
        return json.loads(row["envelope"])
