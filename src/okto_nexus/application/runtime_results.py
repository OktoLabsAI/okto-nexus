"""Publish captured conversation results through canonical message policy.

Only a correlated, durable inbox operation can supply this internal principal.
Native payload fields never select sender, audience, workspace or approval.
"""
import json

from ..errors import ErrorCode, OktoNexusError


class RuntimeResultService:
    def __init__(self, *, connection_factory, agents, endpoints, config):
        self.cf, self.agents, self.endpoints, self.config = connection_factory, agents, endpoints, config

    @staticmethod
    def row(uow, result_id):
        row = uow.connection.execute("SELECT r.*,o.recipient_agent_id,o.actor_agent_id,o.credential_binding,"
            "o.endpoint_id,o.endpoint_revision,o.profile_revision,o.workspace_id,o.message_id AS parent_id,"
            "o.terminal_event_id,m.from_agent_id AS recipient_id,m.channel_id,w.root_realpath "
            "FROM runtime_results r JOIN delivery_outbox o ON o.operation_id=r.operation_id "
            "JOIN messages m ON m.message_id=o.message_id JOIN workspaces w ON w.workspace_id=o.workspace_id "
            "WHERE r.result_id=?", (result_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def arguments(row):
        body = row["output_text"] or "The runtime returned no textual output."
        raw = body.encode("utf-8")
        if len(raw) > 60000:
            body = raw[:60000].decode("utf-8", errors="ignore") + "\n[Preview truncated; full captured result requires authorized runtime access.]"
        return {"project_root": row["root_realpath"], "from_agent_id": row["recipient_agent_id"],
            "subject": "Runtime result", "body": body, "channel_id": row["channel_id"],
            "parent_message_id": row["parent_id"],
            "target": {"strategy": "direct", "agent_id": row["recipient_id"]}}

    def authorize(self, uow, *, result_id, supplied, approved=False):
        row = self.row(uow, result_id)
        if not self.config.feature_harness_integrations or not row or row["terminal_event_id"] != row["event_id"]:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "No authorized captured result.", {})
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
            "publication_approval_id=COALESCE(?,publication_approval_id),publication_response=? WHERE result_id=?",
            ("PENDING_APPROVAL" if pending else "PUBLISHED", response.get("message_id"),
             response.get("approval_id"), json.dumps(response, ensure_ascii=False, sort_keys=True), result_id))

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
