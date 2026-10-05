"""Owner-only journal maintenance; no filesystem work in a database UoW."""
from ..errors import ErrorCode, OktoNexusError
from ..domain.base import new_id
from .runtime_results import RuntimeResultService
import hashlib
import json


class RuntimeMaintenanceService:
    def __init__(self, *, access, dispatcher, artifact_store=None):
        self.access, self.dispatcher = access, dispatcher
        self.artifact_store = artifact_store

    def _authorize_owner(self, context):
        self.access.authorize(context, action="admin")
        owner = self.dispatcher
        with owner.cf.unit_of_work(write=False) as uow:
            valid = owner.repo.owns(uow, owner_id=owner.owner_id, epoch=owner.epoch, now=owner.clock.now_iso())
        if not valid or owner._quiescing.is_set() or owner._stop.is_set():
            raise OktoNexusError(ErrorCode.CONFLICT, "Runtime maintenance requires the active serve owner.", {})
        return owner

    def journal(self, context, *, compact=False):
        owner = self._authorize_owner(context)
        try:
            result = owner.event_ingress.compact() if compact else owner.event_ingress.journal.diagnostics()
        except OSError:
            raise OktoNexusError(ErrorCode.CONFLICT, "Journal maintenance failed; preserve the store and inspect its recovery state.", {}) from None
        if compact:
            owner.wake()
        return result

    def artifacts(self, context, *, action="inspect", result_id=None, quota_bytes=None, idempotency_key=None, reason=None):
        owner = self._authorize_owner(context)
        if action == "inspect":
            if any(value is not None for value in (result_id, quota_bytes, idempotency_key, reason)):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Inspection does not accept mutation parameters.", {})
            with owner.cf.unit_of_work(write=False) as uow:
                quota = uow.connection.execute("SELECT quota_bytes FROM runtime_artifact_settings").fetchone()[0]
                used = uow.connection.execute("SELECT COALESCE(sum(artifact_reserved_bytes),0) FROM runtime_results").fetchone()[0]
                results = [dict(row) for row in uow.connection.execute("SELECT result_id,publication_state,publication_reason,"
                    "artifact_reserved_bytes,artifact_generation,output_artifact_id FROM runtime_results "
                    "WHERE artifact_reserved_bytes>0 OR publication_state IN ('BLOCKED','REVIEW_REQUIRED','ARTIFACT_CLEANUP') "
                    "ORDER BY captured_at,result_id LIMIT 100")]
                pending = [dict(row) for row in uow.connection.execute("SELECT maintenance_id,result_id,action,status,created_at,idempotency_key,reason "
                    "FROM runtime_result_maintenance WHERE status='PENDING' ORDER BY created_at LIMIT 100")]
            return {"quota_bytes": quota, "agent_quota_bytes": quota // 4, "workspace_quota_bytes": quota // 2,
                "reserved_bytes": used, "results": results, "pending_maintenance": pending}
        if (not isinstance(action, str) or action not in {"cleanup", "retry", "quota"} or not isinstance(idempotency_key, str) or
                not 1 <= len(idempotency_key) <= 128 or not isinstance(reason, str) or not 1 <= len(reason) <= 512 or not reason.strip()):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Maintenance requires action, idempotency key and audit reason.", {})
        if action == "quota":
            if result_id is not None or type(quota_bytes) is not int or not 262144 <= quota_bytes <= 1073741824:
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Artifact quota must be 256 KiB..1 GiB, without result_id.", {})
        elif quota_bytes is not None or not isinstance(result_id, str) or not 1 <= len(result_id) <= 128:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Cleanup/retry requires result_id, without quota_bytes.", {})
        digest = hashlib.sha256(json.dumps([action, result_id, quota_bytes, reason], ensure_ascii=False).encode()).hexdigest()
        actor = context.actor_agent_id or "operator"
        now = owner.clock.now_iso()
        with owner.cf.unit_of_work() as uow:
            self.access.authorize(context, action="admin", uow=uow)
            existing = uow.connection.execute("SELECT * FROM runtime_result_maintenance WHERE actor_agent_id=? AND idempotency_key=?",
                (actor, idempotency_key)).fetchone()
            if existing:
                if existing["request_hash"] != digest:
                    raise OktoNexusError(ErrorCode.CONFLICT, "Maintenance key already binds another request.", {})
                if existing["status"] == "DONE":
                    return json.loads(existing["response"])
                if action != "cleanup":
                    raise OktoNexusError(ErrorCode.CONFLICT, "Unexpected incomplete maintenance record.", {})
                operation = dict(existing)
            else:
                source = RuntimeResultService.row(uow, result_id) if result_id else None
                if action != "quota" and (not source or source["publication_state"] not in {"BLOCKED", "REVIEW_REQUIRED"}
                        or source["publication_message_id"] or source["output_artifact_id"]):
                    raise OktoNexusError(ErrorCode.CONFLICT, "Only unpublished blocked/review results can be maintained.", {})
                artifact_id = RuntimeResultService.artifact_id(source) if source else None
                if action == "cleanup" and (not source["artifact_reserved_bytes"] or not artifact_id):
                    raise OktoNexusError(ErrorCode.CONFLICT, "Result has no prepared artifact reservation.", {})
                if action == "cleanup" and uow.connection.execute("SELECT 1 FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone():
                    raise OktoNexusError(ErrorCode.CONFLICT, "Catalogued artifacts cannot be discarded by runtime cleanup.", {})
                mid = new_id("maintenance")
                operation = {"maintenance_id": mid, "result_id": result_id, "artifact_id": artifact_id,
                    "artifact_generation": source["artifact_generation"] if source else None,
                    "workspace_id": source["workspace_id"] if source else None,
                    "agent_id": source["recipient_agent_id"] if source else None,
                    "reserved_bytes": source["artifact_reserved_bytes"] if source else 0}
                uow.connection.execute("INSERT INTO runtime_result_maintenance(maintenance_id,actor_agent_id,idempotency_key,"
                    "request_hash,action,result_id,artifact_id,artifact_generation,workspace_id,agent_id,reserved_bytes,reason,status,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'PENDING',?,?)", (mid, actor, idempotency_key, digest, action,
                    result_id, artifact_id, operation["artifact_generation"], operation["workspace_id"], operation["agent_id"],
                    operation["reserved_bytes"], reason, now, now))
                if action == "cleanup":
                    uow.connection.execute("UPDATE runtime_results SET publication_state='ARTIFACT_CLEANUP' WHERE result_id=?", (result_id,))
                else:
                    if action == "retry":
                        uow.connection.execute("UPDATE runtime_results SET publication_state='PENDING_AUTHORIZATION',publication_reason=NULL,"
                            "publication_approval_id=NULL,publication_response=NULL WHERE result_id=?", (result_id,))
                    else:
                        used = uow.connection.execute("SELECT COALESCE(sum(artifact_reserved_bytes),0) FROM runtime_results").fetchone()[0]
                        per_agent = uow.connection.execute("SELECT COALESCE(max(n),0) FROM (SELECT sum(r.artifact_reserved_bytes) n "
                            "FROM runtime_results r JOIN delivery_outbox o ON o.operation_id=r.operation_id GROUP BY o.recipient_agent_id)").fetchone()[0]
                        per_workspace = uow.connection.execute("SELECT COALESCE(max(n),0) FROM (SELECT sum(r.artifact_reserved_bytes) n "
                            "FROM runtime_results r JOIN delivery_outbox o ON o.operation_id=r.operation_id GROUP BY o.workspace_id)").fetchone()[0]
                        if used > quota_bytes or per_agent > quota_bytes // 4 or per_workspace > quota_bytes // 2:
                            raise OktoNexusError(ErrorCode.CONFLICT, "Quota cannot be lowered below retained reservations.", {})
                        uow.connection.execute("UPDATE runtime_artifact_settings SET quota_bytes=?", (quota_bytes,))
                    response = {"maintenance_id": mid, "action": action, "state": "DONE", "result_id": result_id,
                        "quota_bytes": quota_bytes, "native_replayed": False}
                    self._complete(uow, operation, response)
        if action != "cleanup":
            owner.wake()
            return response
        try:
            report = self.artifact_store.discard_unpublished(workspace_id=operation["workspace_id"],
                agent_id=operation["agent_id"], artifact_id=operation["artifact_id"])
            if report.get("absent") is not True:
                raise OSError("Artifact absence was not verified")
        except Exception:
            raise OktoNexusError(ErrorCode.CONFLICT, "Artifact cleanup remains pending; retry the same maintenance key.",
                {"maintenance_id": operation["maintenance_id"]}) from None
        with owner.cf.unit_of_work() as uow:
            current = uow.connection.execute("SELECT * FROM runtime_result_maintenance WHERE maintenance_id=?", (operation["maintenance_id"],)).fetchone()
            if current["status"] == "DONE":
                return json.loads(current["response"])
            changed = uow.connection.execute("UPDATE runtime_results SET publication_state='BLOCKED',artifact_reserved_bytes=0,"
                "artifact_generation=artifact_generation+1 WHERE result_id=? AND publication_state='ARTIFACT_CLEANUP' "
                "AND artifact_generation=? AND output_artifact_id IS NULL AND publication_message_id IS NULL",
                (operation["result_id"], operation["artifact_generation"]))
            if changed.rowcount != 1:
                raise OktoNexusError(ErrorCode.CONFLICT, "Artifact cleanup binding changed; reservation remains fenced.", {})
            response = {"maintenance_id": operation["maintenance_id"], "action": "cleanup", "state": "DONE",
                "result_id": operation["result_id"], "released_bytes": operation["reserved_bytes"],
                "removed_directories": report["removed_directories"], "native_replayed": False}
            self._complete(uow, operation, response)
        return response

    def _complete(self, uow, operation, response):
        uow.connection.execute("UPDATE runtime_result_maintenance SET status='DONE',response=?,updated_at=? WHERE maintenance_id=?",
            (json.dumps(response, sort_keys=True), self.dispatcher.clock.now_iso(), operation["maintenance_id"]))
