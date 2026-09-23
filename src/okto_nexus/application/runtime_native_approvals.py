"""Durable native request decisions using canonical human approvals.

The journal supplies request provenance. Decisions remain distinct from native
transport writes, and ambiguous writes are never automatically replayed.
"""
import json

from ..errors import ErrorCode, OktoNexusError
from ..domain.runtime_commands import RuntimeCommandNotSent

ACTION = "runtime_native_approval"


class RuntimeNativeApprovalService:
    def __init__(self, *, owner, supervisor, approvals, config, validate_delivery, validate_command):
        self.owner, self.supervisor, self.approvals, self.config = owner, supervisor, approvals, config
        self.validate_delivery, self.validate_command = validate_delivery, validate_command
        approvals.register_executor(ACTION, self.decision_ready, idempotent_decisions=True)
        approvals.register_decision_listener(ACTION, owner.wake)

    def decision_ready(self, kwargs):
        # ApprovalService already committed the canonical human decision.
        # No native call happens in this executor; recovery scans approved rows
        # even if the process stops between this hint and its receipt commit.
        try:
            self.owner.wake()
        except Exception:
            pass
        return {"native_event_id": kwargs["native_event_id"], "durable": True,
                "external_acceptance": "not_observed"}

    def owns(self, uow):
        return not self.owner._stop.is_set() and self.owner.repo.owns(
            uow, owner_id=self.owner.owner_id, epoch=self.owner.epoch, now=self.owner.clock.now_iso())

    def validate(self, uow, row):
        if not self.config.feature_harness_integrations or not self.config.feature_hitl:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Native approvals are disabled.", {})
        table = row["source_kind"]
        if table not in {"delivery_outbox", "runtime_commands"}:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Native approval source is unavailable.", {})
        source = uow.connection.execute(f"SELECT * FROM {table} WHERE operation_id=?", (row["operation_id"],)).fetchone()
        if (not source or source["terminal_event_id"] or source["owner_epoch"] != self.owner.epoch or
                row["owner_epoch"] != self.owner.epoch or source["runtime_session_id"] != row["runtime_session_id"] or
                (source["native_thread_id"] or "") != row["native_thread_id"] or (source["native_turn_id"] or "") != row["native_turn_id"]):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Native approval turn is no longer current.", {})
        (self.validate_delivery if table == "delivery_outbox" else self.validate_command)(uow, dict(source))
        session = self.supervisor.get(row["runtime_session_id"])
        if not session or session.connection_id != row["connection_id"] or session.owner_epoch != self.owner.epoch:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Native approval connection is no longer current.", {})
        return source, session

    def scan_once(self):
        if self.owner._stop.is_set() or self.owner._quiescing.is_set():
            return 0
        processed = 0
        with self.owner.cf.unit_of_work() as uow:
            if not self.owns(uow):
                return 0
            # A former owner may have written a reply; never replay that reply.
            uow.connection.execute("UPDATE runtime_native_approvals SET state=CASE WHEN state='SENDING' THEN 'OUTCOME_UNKNOWN' ELSE 'NOT_SENT' END,"
                "reason='owner_changed' WHERE owner_epoch<>? AND state IN ('NEW','PENDING','SENDING')", (self.owner.epoch,))
            rows = uow.connection.execute("SELECT * FROM runtime_native_approvals WHERE state='NEW' ORDER BY created_at,event_id LIMIT 8").fetchall()
            for row in rows:
                reason, approval_id = None, None
                try:
                    source, session = self.validate(uow, row)
                    count = uow.connection.execute("SELECT count(*) FROM runtime_native_approvals WHERE state='PENDING' AND approval_id IS NOT NULL").fetchone()[0]
                    if count >= 256:
                        raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Native approval capacity exhausted.", {})
                    request = json.loads(row["request_payload"])
                    created = self.approvals.intercept(uow, workspace_id=session.workspace_id,
                        agent_id=session.owning_agent_id, action=ACTION, policy_id="native-runtime-request-v1",
                        kwargs={"native_event_id": row["event_id"], "operation_id": row["operation_id"],
                                "request_hash": row["request_hash"], "payload": request})
                    approval_id = created["approval_id"]
                except OktoNexusError as exc:
                    reason = str(exc.code)
                uow.connection.execute("UPDATE runtime_native_approvals SET state='PENDING',approval_id=?,reason=? WHERE event_id=?",
                                       (approval_id, reason, row["event_id"]))
                processed += 1
        with self.owner.cf.unit_of_work(write=False) as uow:
            rows = uow.connection.execute("SELECT n.*,a.status AS approval_status FROM runtime_native_approvals n "
                "LEFT JOIN approvals a ON a.approval_id=n.approval_id WHERE n.state='PENDING' AND "
                "(n.approval_id IS NULL OR a.status IN ('approved','rejected') OR n.expires_at<=?) "
                "ORDER BY n.created_at,n.event_id LIMIT 8", (self.owner.clock.now_iso(),)).fetchall()
        for row in rows:
            self.respond(dict(row))
            processed += 1
        return processed

    def respond(self, row):
        decision = "accept" if row["approval_status"] == "approved" else "decline"
        reason = row["reason"]
        with self.owner.cf.unit_of_work() as uow:
            if not self.owns(uow):
                return
            if row["expires_at"] <= self.owner.clock.now_iso():
                decision, reason = "decline", "expired"
            try:
                self.validate(uow, row)
            except OktoNexusError:
                decision, reason = "decline", "authority_or_turn_changed"
            changed = uow.connection.execute("UPDATE runtime_native_approvals SET state='SENDING',decision=?,reason=? "
                "WHERE event_id=? AND state='PENDING'", (decision, reason, row["event_id"])).rowcount
        if not changed:
            return
        def before_write():
            actual, why = decision, reason
            with self.owner.cf.unit_of_work() as uow:
                if not self.owns(uow) or self.owner._quiescing.is_set():
                    raise RuntimeCommandNotSent("Native approval owner stopped before write")
                current = uow.connection.execute("SELECT state FROM runtime_native_approvals WHERE event_id=?", (row["event_id"],)).fetchone()
                if not current or current["state"] != "SENDING":
                    raise RuntimeCommandNotSent("Native approval response already settled")
                try:
                    self.validate(uow, row)
                    if row["expires_at"] <= self.owner.clock.now_iso():
                        actual, why = "decline", "expired"
                except OktoNexusError:
                    actual, why = "decline", "authority_or_turn_changed"
                uow.connection.execute("UPDATE runtime_native_approvals SET decision=?,reason=? WHERE event_id=?",
                                       (actual, why, row["event_id"]))
            return actual
        outcome = "SENT_UNCONFIRMED"
        try:
            self.supervisor.reply_native_approval(row["runtime_session_id"], connection_id=row["connection_id"],
                owner_epoch=row["owner_epoch"], request=json.loads(row["request_payload"]), decision=decision, before_write=before_write)
        except RuntimeCommandNotSent:
            outcome = "NOT_SENT"
        except Exception:
            # A timed-out write may still be accepted. Do not turn expiry or
            # transport failure into permission to resend an approval.
            outcome = "OUTCOME_UNKNOWN"
        with self.owner.cf.unit_of_work() as uow:
            if self.owns(uow):
                uow.connection.execute("UPDATE runtime_native_approvals SET state=? WHERE event_id=? AND state='SENDING'",
                                       (outcome, row["event_id"]))
