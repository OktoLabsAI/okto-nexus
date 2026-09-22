"""Persistent open idempotency; unresolved starts never auto-spawn again."""
from ....domain.base import new_id
from ....errors import ErrorCode, OktoNexusError


class SqliteRuntimeRequestRepo:
    def reserve(self, uow, *, actor_id, key, request_hash, now):
        row = uow.connection.execute(
            "SELECT * FROM runtime_open_requests WHERE actor_agent_id=? AND idempotency_key=?", (actor_id, key)).fetchone()
        if row:
            if row["request_hash"] != request_hash:
                raise OktoNexusError(ErrorCode.CONFLICT, "Idempotency key already binds different runtime parameters.", {})
            session = uow.connection.execute("SELECT session_id FROM harness_sessions WHERE open_request_id=?", (row["request_id"],)).fetchone()
            if session:
                return row["request_id"], session[0]
            raise OktoNexusError(ErrorCode.CONFLICT, "Runtime request is pending or requires reconciliation; it will not be replayed.", {})
        request_id = new_id("open")
        uow.connection.execute(
            "INSERT INTO runtime_open_requests(request_id,actor_agent_id,idempotency_key,request_hash,status,created_at) VALUES(?,?,?,?,'RESERVED',?)",
            (request_id, actor_id, key, request_hash, now))
        return request_id, None

    def finish(self, uow, *, request_id, status):
        uow.connection.execute("UPDATE runtime_open_requests SET status=? WHERE request_id=? AND status='RESERVED'", (status, request_id))
