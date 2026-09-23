"""Publish captured conversation results through canonical message policy.

Only a correlated, durable inbox operation can supply this internal principal.
Native payload fields never select sender, audience, workspace or approval.
"""
import json
import hashlib

from ..errors import ErrorCode, OktoNexusError
from ..domain.runtime_context import RuntimeRequestContext
from ..domain.inbox import requires_known_recipient
from ..domain.tag_selector import reachable
from ..domain.targets import target_strategy
from .permissions import permission_set_for


class RuntimeResultService:
    ARTIFACT_QUOTA_BYTES = 64 * 1024 * 1024
    def __init__(self, *, connection_factory, agents, endpoints, config, artifacts=None, owner_provider=None, work_validator=None):
        self.cf, self.agents, self.endpoints, self.config = connection_factory, agents, endpoints, config
        self.artifacts = artifacts
        self.owner_provider = owner_provider
        self.work_validator = work_validator

    @staticmethod
    def artifact_id(row):
        if len((row["output_text"] or "").encode("utf-8")) > 60000 or row["output_truncated"]:
            identity = row["result_id"] + (":" + str(row["artifact_generation"]) if row.get("artifact_generation", 0) else "")
            return "art_runtime_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return None

    @staticmethod
    def row(uow, result_id):
        row = uow.connection.execute("SELECT r.*,o.recipient_agent_id,o.actor_agent_id,o.credential_binding,"
            "o.endpoint_id,o.endpoint_revision,o.profile_revision,o.workspace_id,o.message_id AS parent_id,"
            "o.terminal_event_id,m.from_agent_id AS recipient_id,m.channel_id,w.root_realpath,e.public_config AS notification_config "
            "FROM runtime_results r JOIN delivery_outbox o ON o.operation_id=r.operation_id "
            "JOIN agent_endpoints e ON e.endpoint_id=o.endpoint_id "
            "JOIN messages m ON m.message_id=o.message_id JOIN workspaces w ON w.workspace_id=o.workspace_id "
            "WHERE r.result_id=?", (result_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def arguments(row):
        body = row["output_text"] or "The runtime returned no textual output."
        raw = body.encode("utf-8")
        if len(raw) > 60000:
            body = raw[:60000].decode("utf-8", errors="ignore") + "\n[Preview truncated; captured output is attached as a private artifact.]"
        artifact_id = RuntimeResultService.artifact_id(row)
        if row["output_truncated"]:
            body += "\n[Captured output exceeded the materialization limit; the artifact is also truncated.]"
        return {"project_root": row["root_realpath"], "from_agent_id": row["recipient_agent_id"],
            "subject": "Runtime result", "body": body, "channel_id": row["channel_id"],
            "parent_message_id": row["parent_id"],
            "target": json.loads(row["notification_config"]).get("notify_target", {"strategy": "direct", "agent_id": row["recipient_id"]}),
            "artifacts": [artifact_id] if artifact_id else []}

    def prepare(self, result_id, *, approved=False):
        with self.cf.unit_of_work(write=False) as uow:
            row = self.row(uow, result_id)
            if not row:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "No authorized captured result.", {})
            existing = self.authorize(uow, result_id=result_id, supplied=self.arguments(row), approved=approved)
        artifact_id = self.artifact_id(row)
        if existing or not artifact_id:
            return None
        if self.artifacts is None:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR, "Runtime artifact storage is not configured.", {})
        with self.cf.unit_of_work() as uow:
            existing = self.authorize(uow, result_id=result_id, supplied=self.arguments(row), approved=approved)
            if existing:
                return None
            current = self.row(uow, result_id)
            if not current["artifact_reserved_bytes"]:
                size = len((row["output_text"] or "").encode("utf-8"))
                usage = uow.connection.execute("SELECT COALESCE(sum(r.artifact_reserved_bytes),0),"
                    "COALESCE(sum(CASE WHEN o.recipient_agent_id=? THEN r.artifact_reserved_bytes ELSE 0 END),0),"
                    "COALESCE(sum(CASE WHEN o.workspace_id=? THEN r.artifact_reserved_bytes ELSE 0 END),0) "
                    "FROM runtime_results r JOIN delivery_outbox o ON o.operation_id=r.operation_id WHERE r.artifact_reserved_bytes>0",
                    (row["recipient_agent_id"], row["workspace_id"])).fetchone()
                configured = uow.connection.execute("SELECT quota_bytes FROM runtime_artifact_settings WHERE singleton=1").fetchone()
                quota = configured[0] if configured else self.ARTIFACT_QUOTA_BYTES
                if any(used + size > limit for used, limit in zip(usage, (quota, quota // 4, quota // 2))):
                    raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Runtime artifact retention quota requires operator maintenance.", {})
                uow.connection.execute("UPDATE runtime_results SET artifact_reserved_bytes=? WHERE result_id=?", (size, result_id))
        # Only the validated serve owner enters this path; previous publication
        # workers retain journal ownership until drained. A recovered staging
        # directory therefore cannot belong to a concurrent native owner.
        return self.artifacts.prepare_runtime_result(artifact_id=artifact_id,
            workspace_id=row["workspace_id"], agent_id=row["recipient_agent_id"], content=row["output_text"] or "",
            result_id=result_id, truncated=row["output_truncated"])

    def commit_artifact(self, uow, *, result_id, prepared, recipients):
        if prepared is None:
            return
        row = self.row(uow, result_id)
        self.artifacts.commit_runtime_result(uow, prepared=prepared,
            readers=[row["recipient_agent_id"], *recipients])

    def authorize_notification_audience(self, uow, *, result_id, recipients):
        row = self.row(uow, result_id)
        target = self.arguments(row)["target"]
        # A private reply is already authorized by the initiating conversation.
        # Explicit dissemination elsewhere also needs the initiating actor's
        # current authority, intersected with the represented sender's gates.
        if (target_strategy(target) == "direct" and target["agent_id"] == row["recipient_id"]) or row["actor_agent_id"] == row["recipient_agent_id"]:
            return None
        actor = self.agents.get(uow, row["actor_agent_id"])
        perms = permission_set_for(self.agents, uow, actor.agent_id)
        if row["channel_id"]:
            perms.require("messages", "send_channel")
            if requires_known_recipient(target):
                perms.require("messages", "send_direct")
        else:
            perms.require("messages", "send_direct" if requires_known_recipient(target) else "send_broadcast")
        if row["publication_state"] == "PUBLISHED":
            captured = json.loads(row["publication_response"])["recipients"]
            if not set(recipients) <= set(captured):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Notification recipient was not admitted.", {})
            recipients = captured
        maximum = perms.limit("max_recipients")
        if maximum > 0 and len(recipients) > maximum:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Notification exceeds originating actor audience limit.", {})
        if any(recipient != actor.agent_id and not reachable(actor, self.agents.get(uow, recipient)) for recipient in recipients):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Notification audience exceeds originating actor authority.", {})
        return actor.agent_id

    def validate_relay(self, uow, result_id):
        first, current, seen = None, result_id, set()
        # Revalidate the bounded authority ancestry, including a managed-work
        # grant when the first result originated from a canonical handoff.
        for _ in range(65):
            if current in seen:
                break
            seen.add(current)
            row = self._validate_relay_source(uow, current)
            first = first or row
            source = uow.connection.execute("SELECT source_result_id FROM delivery_outbox WHERE operation_id=?",
                (row["operation_id"],)).fetchone()
            if not source or not source[0]:
                return first
            current = source[0]
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Relay authority ancestry is invalid.", {})

    def _validate_relay_source(self, uow, result_id):
        row = self.row(uow, result_id)
        if not row:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Relay source unavailable.", {})
        self.authorize(uow, result_id=result_id, supplied=self.arguments(row),
                       approved=row["publication_state"] == "PENDING_APPROVAL")
        endpoint = self.endpoints.get(uow, row["endpoint_id"])
        if not endpoint["public_config"].get("relay_results") or row["delivery_outcome"] != "success":
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Result relay is not authorized or source did not succeed.", {})
        return row

    def enqueue_relay(self, uow, *, result_id, planner, message, delivery, now, authorization_revision, emitter):
        row = self.row(uow, result_id)
        endpoint = self.endpoints.get(uow, row["endpoint_id"])
        if not endpoint["public_config"].get("relay_results"):
            return None
        # Publication and private output survive a blocked relay. Roll back only
        # its admission/budget/transport reservation, within this same transaction.
        uow.connection.execute("SAVEPOINT result_relay")
        try:
            row = self.validate_relay(uow, result_id)
            if row["recipient_agent_id"] == delivery.recipient_agent_id:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Automatic result self-loop is prohibited.", {})
            context = RuntimeRequestContext(row["actor_agent_id"], "captured_result",
                represented_agent_id=row["recipient_agent_id"], credential_binding=row["credential_binding"])
            operation = planner.enqueue(uow, context=context, message=message, delivery=delivery, now=now,
                authorization_revision=authorization_revision, result_source=row)
        except OktoNexusError as exc:
            uow.connection.execute("ROLLBACK TO result_relay")
            state, reason, operation = "BLOCKED", str(exc.code), None
        else:
            state, reason = ("ENQUEUED", None) if operation else ("NO_ENDPOINT", "No eligible conversation endpoint")
        finally:
            uow.connection.execute("RELEASE result_relay")
        uow.connection.execute("INSERT INTO runtime_relay_decisions VALUES(?,?,?,?,?,?)",
            (result_id, delivery.delivery_id, operation, state, reason, now))
        if state == "BLOCKED":
            emitter.emit(uow, workspace_id=message.workspace_id, stream="agent", type="runtime.relay_blocked",
                actor_agent_id=message.from_agent_id, visibility="eligible",
                target=json.dumps({"strategy": "direct", "agent_id": message.from_agent_id}),
                payload={"result_id": result_id, "message_id": message.message_id,
                         "delivery_id": delivery.delivery_id, "reason": reason})
        states = {r[0] for r in uow.connection.execute("SELECT state FROM runtime_relay_decisions WHERE result_id=?", (result_id,))}
        aggregate = "PARTIAL" if "ENQUEUED" in states and len(states) > 1 else "BLOCKED" if "BLOCKED" in states else state
        uow.connection.execute("UPDATE runtime_results SET relay_state=?,relay_reason=? WHERE result_id=?",
            (aggregate, "Some recipient relays were not admitted" if aggregate == "PARTIAL" else reason, result_id))
        return operation

    def authorize(self, uow, *, result_id, supplied, approved=False):
        owner = self.owner_provider() if self.owner_provider else None
        if (not owner or owner._stop.is_set() or not owner.repo.owns(uow, owner_id=owner.owner_id,
                epoch=owner.epoch, now=owner.clock.now_iso())):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Result publication requires the current serve owner.", {})
        row = self.row(uow, result_id)
        if not self.config.feature_harness_integrations or not row or row["terminal_event_id"] != row["event_id"]:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "No authorized captured result.", {})
        if uow.connection.execute("SELECT 1 FROM runtime_handoff_bindings WHERE operation_id=?", (row["operation_id"],)).fetchone():
            if not self.work_validator:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Managed work publication is unavailable.", {})
            operation = dict(uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?", (row["operation_id"],)).fetchone())
            self.work_validator(uow, operation=operation)
        endpoint = self.endpoints.get(uow, row["endpoint_id"])
        sender = self.agents.get(uow, row["recipient_agent_id"])
        actor = self.agents.get(uow, row["actor_agent_id"])
        recipient = self.agents.get(uow, row["recipient_id"])
        profile = self.endpoints.profile(uow, endpoint["profile_id"]) if endpoint and endpoint["profile_id"] else None
        if (not endpoint or not endpoint["enabled"] or endpoint["response_policy"] != "conversation" or
                endpoint["revision"] != row["endpoint_revision"] or
                not sender or not sender.is_active or not recipient or not recipient.is_active or
                not actor or not actor.is_active or actor.api_key_hash != row["credential_binding"] or
                (endpoint["profile_id"] and (not profile or not profile["enabled"] or profile["revision"] != row["profile_revision"]))):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Result publication authority changed.", {})
        expected = self.arguments(row)
        if supplied != expected:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Result publication cannot replace its source or audience.", {})
        if approved and row["publication_state"] != "PUBLISHED":
            approval = uow.connection.execute("SELECT status FROM approvals WHERE approval_id=?",
                (row["publication_approval_id"],)).fetchone()
            if not approval or approval["status"] != "approved":
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Result publication has no approved canonical decision.", {})
        if row["publication_state"] == "PUBLISHED" or row["publication_state"] == "PENDING_APPROVAL" and not approved:
            return json.loads(row["publication_response"])
        if row["publication_state"] not in {"PENDING_AUTHORIZATION", "PENDING_APPROVAL"}:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Result publication is blocked.", {})
        return None

    @staticmethod
    def finish(uow, *, result_id, response):
        pending = response.get("status") == "pending_approval"
        uow.connection.execute("UPDATE runtime_results SET publication_state=?,publication_message_id=?,"
            "publication_approval_id=COALESCE(?,publication_approval_id),publication_response=?,"
            "output_artifact_id=COALESCE(?,output_artifact_id) WHERE result_id=?",
            ("PENDING_APPROVAL" if pending else "PUBLISHED", response.get("message_id"),
             response.get("approval_id"), json.dumps(response, ensure_ascii=False, sort_keys=True),
             next(iter(response.get("artifacts") or []), None), result_id))

    def scan_once(self, messages):
        if not self.config.feature_harness_integrations:
            return 0
        with self.cf.unit_of_work() as uow:
            uow.connection.execute("UPDATE runtime_results SET publication_state='BLOCKED',publication_reason='approval_rejected' "
                "WHERE publication_state='PENDING_APPROVAL' AND publication_approval_id IN "
                "(SELECT approval_id FROM approvals WHERE status='rejected')")
        with self.cf.unit_of_work(write=False) as uow:
            rows = uow.connection.execute("SELECT result_id FROM runtime_results WHERE publication_state='PENDING_AUTHORIZATION' "
                "AND operation_id IS NOT NULL ORDER BY captured_at,result_id LIMIT 4").fetchall()
            pending = [self.row(uow, row["result_id"]) for row in rows]
        for row in pending:
            if row is None:
                continue
            try:
                messages.create_message(**self.arguments(row), _runtime_result_id=row["result_id"])
            except OktoNexusError as exc:
                # Canonical services already audit policy denials. Keep native
                # output private and do not recursively send an error message.
                with self.cf.unit_of_work() as uow:
                    uow.connection.execute("UPDATE runtime_results SET publication_state='BLOCKED',publication_reason=? "
                        "WHERE result_id=? AND publication_state='PENDING_AUTHORIZATION'",
                        (str(exc.code), row["result_id"]))
        return len(rows)
