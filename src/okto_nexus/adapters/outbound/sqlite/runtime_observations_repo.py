"""Nonexecuting observation transport state; no logical delivery mutations."""
import sqlite3

from ....domain.base import utc_now_iso
from ....errors import ErrorCode, OktoNexusError
from .runtime_outbox_repo import require_capture_available


class SqliteRuntimeObservationRepo:
    def __init__(self, clock=None):
        self.clock = clock

    def enqueue(self, uow, *, source_operation_id, envelope, endpoint, profile, session, now):
        require_capture_available(uow)
        count = uow.connection.execute("SELECT count(*) FROM runtime_context_observations o "
            "JOIN agent_endpoints e USING(endpoint_id) WHERE e.agent_id=? "
            "AND o.status IN ('PENDING','CLAIMED','SENDING','OUTCOME_UNKNOWN')", (endpoint["agent_id"],)).fetchone()[0]
        workspace_count = uow.connection.execute("SELECT count(*) FROM runtime_context_observations o "
            "JOIN agent_endpoints e USING(endpoint_id) WHERE e.workspace_id=? "
            "AND o.status IN ('PENDING','CLAIMED','SENDING','OUTCOME_UNKNOWN')", (endpoint["workspace_id"],)).fetchone()[0]
        if count >= 32 or workspace_count >= 128:
            raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Runtime observation capacity exhausted.", {})
        try:
            uow.connection.execute("INSERT INTO runtime_context_observations(operation_id,source_operation_id,"
                "endpoint_id,endpoint_revision,profile_revision,runtime_session_id,expected_owner_epoch,envelope,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)", (envelope.operation_id, source_operation_id, endpoint["endpoint_id"],
                    endpoint["revision"], profile["revision"] if profile else None, session["session_id"],
                    session["owner_epoch"], envelope.canonical_json(), now, now))
        except sqlite3.IntegrityError as exc:
            if str(exc) == "runtime_context_backpressure":
                raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Runtime observation capacity exhausted.", {}) from exc
            raise

    def pending(self, uow, *, limit, **_):
        now = self.clock.now_iso() if self.clock else utc_now_iso()
        uow.connection.execute("UPDATE runtime_context_observations SET status='CANCELLED',"
            "reason='observation_session_closed_before_send',updated_at=? WHERE status='PENDING' "
            "AND NOT EXISTS(SELECT 1 FROM harness_sessions s WHERE s.session_id=runtime_session_id "
            "AND s.lifecycle_state='protocol_ready' AND s.owner_epoch=expected_owner_epoch)", (now,))
        return [dict(row, verb="observe_context") for row in uow.connection.execute(
            "SELECT o.* FROM runtime_context_observations o WHERE o.status='PENDING' "
            "AND NOT EXISTS(SELECT 1 FROM runtime_context_observations busy WHERE busy.endpoint_id=o.endpoint_id "
            "AND busy.runtime_session_id=o.runtime_session_id "
            "AND busy.status IN ('CLAIMED','SENDING','OUTCOME_UNKNOWN')) "
            "AND NOT EXISTS(SELECT 1 FROM runtime_context_observations earlier WHERE earlier.endpoint_id=o.endpoint_id "
            "AND earlier.runtime_session_id=o.runtime_session_id "
            "AND earlier.status='PENDING' AND (earlier.created_at,earlier.operation_id)<(o.created_at,o.operation_id)) "
            "ORDER BY o.created_at,o.operation_id LIMIT ?", (limit,))]

    def claim(self, uow, *, operation_id, epoch, attempt_id, now):
        return uow.connection.execute("UPDATE runtime_context_observations SET status='CLAIMED',owner_epoch=?,"
            "attempt_id=?,updated_at=? WHERE operation_id=? AND status='PENDING' AND expected_owner_epoch=?",
            (epoch, attempt_id, now, operation_id, epoch)).rowcount == 1

    def observe(self, uow, *, operation_id, epoch, attempt_id, expected, status, now, reason=None, result=None):
        return uow.connection.execute("UPDATE runtime_context_observations SET status=?,reason=?,updated_at=? "
            "WHERE operation_id=? AND owner_epoch=? AND attempt_id=? AND status=?",
            (status, reason, now, operation_id, epoch, attempt_id, expected)).rowcount == 1

    def recover(self, uow, *, epoch, now):
        uow.connection.execute("UPDATE runtime_context_observations SET status='OUTCOME_UNKNOWN',"
            "reason='owner_lost',updated_at=? WHERE status='SENDING'", (now,))
        uow.connection.execute("UPDATE runtime_context_observations SET status='CANCELLED',"
            "reason='observation_session_owner_lost',updated_at=? WHERE status IN ('PENDING','CLAIMED') "
            "AND expected_owner_epoch<>?", (now, epoch))

    def list_for_source(self, uow, operation_id):
        return [dict(row) for row in uow.connection.execute("SELECT operation_id,endpoint_id,runtime_session_id,"
            "status,reason,owner_epoch,attempt_id FROM runtime_context_observations WHERE source_operation_id=? "
            "ORDER BY created_at,operation_id", (operation_id,))]
