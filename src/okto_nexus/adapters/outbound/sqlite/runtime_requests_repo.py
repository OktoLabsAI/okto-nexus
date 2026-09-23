"""Persistent open idempotency; unresolved starts never auto-spawn again."""
from ....domain.base import iso_plus, new_id
from ....errors import ErrorCode, OktoNexusError


class SqliteRuntimeRequestRepo:
    def reserve(self, uow, *, actor_id, key, request_hash, now, endpoint=None, profile=None, owner=None):
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
        if endpoint is not None:
            current = uow.connection.execute("SELECT * FROM runtime_dispatcher_owner WHERE owner_key='dispatcher'").fetchone()
            if (not current or current["lease_expires_at"] <= now or not owner or
                    (current["owner_id"], current["epoch"]) != owner):
                raise OktoNexusError(ErrorCode.CONFLICT, "Runtime opening lost ownership before reservation.", {})
            binding = uow.connection.execute("SELECT revision,health FROM agent_endpoints WHERE endpoint_id=?", (endpoint["endpoint_id"],)).fetchone()
            if not binding or binding["revision"] != endpoint["revision"] or binding["health"] == "quarantined":
                raise OktoNexusError(ErrorCode.CONFLICT, "Runtime binding changed or requires reconciliation.", {})
        uow.connection.execute(
            "INSERT INTO runtime_open_requests(request_id,actor_agent_id,idempotency_key,request_hash,status,created_at) VALUES(?,?,?,?,'RESERVED',?)",
            (request_id, actor_id, key, request_hash, now))
        if endpoint is not None:
            uow.connection.execute("UPDATE runtime_open_requests SET endpoint_id=?,endpoint_revision=?,profile_revision=?,owner_id=?,owner_epoch=?,deadline=? WHERE request_id=?",
                (endpoint["endpoint_id"], endpoint["revision"], profile["revision"] if profile else None,
                 owner[0], owner[1], iso_plus(now, 40), request_id))
        return request_id, None

    def validate_start(self, uow, *, request_id, endpoint_id, now):
        row = uow.connection.execute("SELECT r.* FROM runtime_open_requests r JOIN runtime_dispatcher_owner o "
            "ON o.owner_id=r.owner_id AND o.epoch=r.owner_epoch JOIN agent_endpoints e ON e.endpoint_id=r.endpoint_id "
            "WHERE r.request_id=? AND r.endpoint_id=? AND r.status='RESERVED' AND r.deadline>? "
            "AND o.lease_expires_at>? AND e.enabled=1 AND e.activation_state='approved' "
            "AND e.health<>'quarantined' AND e.revision=r.endpoint_revision "
            "AND (e.profile_id IS NULL OR EXISTS (SELECT 1 FROM runtime_profiles p WHERE p.profile_id=e.profile_id "
            "AND p.enabled=1 AND p.revision=r.profile_revision))", (request_id, endpoint_id, now, now)).fetchone()
        if not row:
            raise OktoNexusError(ErrorCode.CONFLICT, "Runtime opening lost its owner, deadline or approved binding.", {})
        return row["owner_epoch"]

    def finish(self, uow, *, request_id, status):
        uow.connection.execute("UPDATE runtime_open_requests SET status=? WHERE request_id=? AND status='RESERVED'", (status, request_id))
