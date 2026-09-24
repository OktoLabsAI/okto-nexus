"""Durable administrative command transport, scoped to a canonical runtime."""
import hashlib
import json
from dataclasses import asdict

from ....domain.base import new_id
from ....errors import ErrorCode, OktoNexusError
from .runtime_outbox_repo import require_capture_available


class SqliteRuntimeCommandRepo:
    def get(self, uow, operation_id):
        row = uow.connection.execute("SELECT * FROM runtime_commands WHERE operation_id=?", (operation_id,)).fetchone()
        return dict(row) if row else None

    def existing(self, uow, *, actor_id, key):
        row = uow.connection.execute("SELECT * FROM runtime_commands WHERE actor_agent_id=? AND idempotency_key=?", (actor_id, key)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def digest(session_id, verb, payload, expected_operation_id, expected_turn_id, expected_owner_epoch):
        return hashlib.sha256(json.dumps([session_id, verb, payload, expected_operation_id, expected_turn_id, expected_owner_epoch],
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def enqueue(self, uow, *, context, key, request_hash, session, endpoint, profile_revision, verb, payload,
                expected_operation_id, expected_turn_id, grant, now, starts_turn):
        if verb in {"send_turn", "steer"}:
            require_capture_available(uow)
        pending = uow.connection.execute("SELECT count(*),COALESCE(sum(length(CAST(payload AS BLOB))),0) FROM runtime_commands "
            "WHERE reconciliation_id IS NULL AND status IN ('PENDING','CLAIMED','SENDING','OUTCOME_UNKNOWN')").fetchone()
        actor = context.actor_agent_id or "operator"
        own = uow.connection.execute("SELECT count(*) FROM runtime_commands WHERE actor_agent_id=? AND reconciliation_id IS NULL "
            "AND status IN ('PENDING','CLAIMED','SENDING','OUTCOME_UNKNOWN')", (actor,)).fetchone()[0]
        represented = uow.connection.execute("SELECT count(*) FROM runtime_commands c JOIN agent_endpoints e ON e.endpoint_id=c.endpoint_id "
            "WHERE e.agent_id=? AND c.reconciliation_id IS NULL AND c.status IN ('PENDING','CLAIMED','SENDING','OUTCOME_UNKNOWN')", (session.owning_agent_id,)).fetchone()[0]
        workspace = uow.connection.execute("SELECT count(*) FROM runtime_commands c JOIN agent_endpoints e ON e.endpoint_id=c.endpoint_id "
            "WHERE e.workspace_id=? AND c.reconciliation_id IS NULL AND c.status IN ('PENDING','CLAIMED','SENDING','OUTCOME_UNKNOWN')", (session.workspace_id,)).fetchone()[0]
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if pending[0] >= 256 or pending[1] + len(encoded.encode()) > 4 * 1024 * 1024 or own >= 32 or represented >= 32 or workspace >= 128:
            raise OktoNexusError(ErrorCode.CONFLICT, "Runtime command backlog capacity exhausted.", {})
        operation_id = new_id("cmd")
        uow.connection.execute("INSERT INTO runtime_commands(operation_id,actor_agent_id,idempotency_key,request_hash,context,"
            "grant_id,grant_revision,runtime_session_id,endpoint_id,endpoint_revision,profile_revision,verb,payload,"
            "expected_owner_epoch,expected_operation_id,expected_turn_id,created_at,updated_at,starts_turn) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (operation_id, actor, key, request_hash, json.dumps(asdict(context)), grant["grant_id"] if grant else None,
             grant["revision"] if grant else None, session.session_id, endpoint["endpoint_id"], endpoint["revision"],
             profile_revision, verb, encoded, session.owner_epoch, expected_operation_id, expected_turn_id, now, now, int(starts_turn)))
        return self.get(uow, operation_id)

    def pending(self, uow, *, control, limit, close_only=False, blocked_agents=()):
        # A control may overtake normal prompts, but never another in-flight
        # control for its binding. Normal turns share the inbox outbox lane.
        selector = "<>" if control else "="
        query = "SELECT c.* FROM runtime_commands c WHERE c.status='PENDING' AND c.verb " + selector + " 'send_turn' "
        if control:
            query += "AND c.verb='close' " if close_only else "AND c.verb<>'close' "
            # Truncate only after selecting the oldest eligible command per
            # endpoint/lane. Duplicate rows must not consume another lane's slot.
            query += "AND NOT EXISTS (SELECT 1 FROM runtime_commands earlier WHERE earlier.endpoint_id=c.endpoint_id "
            query += "AND earlier.status='PENDING' AND "
            query += "earlier.verb='close' " if close_only else "earlier.verb NOT IN ('close','send_turn') "
            query += "AND (earlier.created_at,earlier.operation_id)<(c.created_at,c.operation_id)) "
        query += "AND NOT EXISTS (SELECT 1 FROM runtime_commands busy WHERE busy.endpoint_id=c.endpoint_id AND busy.reconciliation_id IS NULL "
        if control:
            query += "AND busy.verb='close' " if close_only else "AND busy.verb<>'send_turn' "
            query += "AND busy.status IN ('CLAIMED','SENDING','OUTCOME_UNKNOWN')) "
        else:
            query += "AND busy.operation_id<>c.operation_id AND ((busy.status IN ('CLAIMED','SENDING','OUTCOME_UNKNOWN')) "
            query += "OR (busy.status IN ('SENT_UNCONFIRMED','ACCEPTED') AND busy.starts_turn=1 AND busy.terminal_event_id IS NULL) "
            query += "OR (busy.status='PENDING' AND (busy.verb<>'send_turn' OR (busy.created_at,busy.operation_id)<(c.created_at,c.operation_id))))) "
            query += "AND NOT EXISTS (SELECT 1 FROM delivery_outbox d WHERE COALESCE(json_extract(d.next_binding,'$.endpoint_id'),d.endpoint_id)=c.endpoint_id AND d.reconciliation_id IS NULL AND "
            query += "(d.status IN ('CLAIMED','SENDING','OUTCOME_UNKNOWN') OR (d.status IN ('SENT_UNCONFIRMED','ACCEPTED') AND d.terminal_event_id IS NULL) "
            query += "OR (d.status IN ('PENDING','RETRY_WAIT') AND (d.created_at,d.operation_id)<(c.created_at,c.operation_id)))) "
        if not control:
            # One unresolved normal native write per represented agent across
            # both transport surfaces. Accepted inference does not hold a write
            # worker; uncertain writes keep their fence until reconciliation.
            query += "AND NOT EXISTS (SELECT 1 FROM runtime_commands active JOIN agent_endpoints ae ON ae.endpoint_id=active.endpoint_id "
            query += "JOIN agent_endpoints ce ON ce.endpoint_id=c.endpoint_id WHERE ae.agent_id=ce.agent_id AND active.verb='send_turn' "
            query += "AND active.reconciliation_id IS NULL AND active.status IN ('CLAIMED','SENDING','OUTCOME_UNKNOWN')) "
            query += "AND NOT EXISTS (SELECT 1 FROM delivery_outbox active JOIN agent_endpoints ce ON ce.endpoint_id=c.endpoint_id "
            query += "WHERE active.recipient_agent_id=ce.agent_id AND active.reconciliation_id IS NULL "
            query += "AND active.status IN ('CLAIMED','SENDING','OUTCOME_UNKNOWN')) "
            if blocked_agents:
                query += "AND NOT EXISTS (SELECT 1 FROM agent_endpoints ce WHERE ce.endpoint_id=c.endpoint_id "
                query += "AND ce.agent_id IN (" + ",".join("?" for _ in blocked_agents) + ")) "
            query = "WITH eligible AS (" + query + "), ranked AS (SELECT c.operation_id,ROW_NUMBER() OVER(" + (
                "PARTITION BY e.agent_id ORDER BY c.created_at,c.operation_id) AS agent_rank "
                "FROM eligible c JOIN agent_endpoints e USING(endpoint_id)) "
                "SELECT c.* FROM eligible c JOIN ranked r USING(operation_id) WHERE r.agent_rank=1 ")
        return [dict(r) for r in uow.connection.execute(query + "ORDER BY c.created_at,c.operation_id LIMIT ?",
            (*blocked_agents, limit) if not control else (limit,))]

    def claim(self, uow, *, operation_id, epoch, attempt_id, now):
        return uow.connection.execute("UPDATE runtime_commands SET status='CLAIMED',owner_epoch=?,attempt_id=?,updated_at=? "
            "WHERE operation_id=? AND status='PENDING'", (epoch, attempt_id, now, operation_id)).rowcount == 1

    def observe(self, uow, *, operation_id, epoch, attempt_id, expected, status, now, reason=None, result=None):
        return uow.connection.execute("UPDATE runtime_commands SET status=?,reason=?,result=COALESCE(?,result),updated_at=? "
            "WHERE operation_id=? AND owner_epoch=? AND attempt_id=? AND status=?",
            (status, reason, json.dumps(result) if result is not None else None, now, operation_id, epoch, attempt_id, expected)).rowcount == 1

    @staticmethod
    def response(row):
        return {"operation_id": row["operation_id"], "session_id": row["runtime_session_id"], "verb": row["verb"],
            "state": row["status"], "durable": True, "external_acceptance": "harness_accepted" if row["ack_level"] == "HARNESS_ACCEPTED" else "not_observed",
            "idempotency_key": row["idempotency_key"], "runtime_contract_version": 3}
