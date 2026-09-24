"""Authenticated runtime command use cases shared by inbound surfaces."""
from collections.abc import Mapping
from dataclasses import replace
from contextlib import contextmanager
import json

from ..domain.base import check_inline_size, new_id
from ..domain.delivery import DeliveryEnvelope
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .runtime_requirements import validate_declared_command, validate_effective_control, validate_effective_capability


def validate_runtime_payload(value, *, required):
    if isinstance(value, str):
        check_inline_size("runtime payload", value, 65536)
        try:
            value = json.loads(value)
        except (ValueError, RecursionError) as exc:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid runtime payload JSON object.", {}) from exc
    if value is None and not required:
        return {}
    if not isinstance(value, Mapping) or (not required and value):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                            "Use a conversational payload object; native options are not accepted.", {})
    check_inline_size("runtime payload", value, 65536)
    if not required:
        return {}
    if "schema_version" in value or isinstance(value.get("content"), list):
        # This is the input projection of DeliveryEnvelope v1. The server owns
        # identity, correlation, trust and execution authority; callers only
        # submit conversational data. Artifacts/work use their canonical APIs.
        content = value.get("content")
        if (set(value) - {"schema_version", "content", "subject", "intent", "response_requested"}
                or type(value.get("schema_version")) is not int or value["schema_version"] != 1
                or not isinstance(content, list) or not content
                or any(not isinstance(item, dict) or set(item) != {"type", "text"}
                    or item["type"] != "text" or not isinstance(item["text"], str) or not item["text"]
                    for item in content)
                or value.get("intent", "conversation") != "conversation"
                or value.get("subject") is not None and not isinstance(value["subject"], str)
                or type(value.get("response_requested", False)) is not bool):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                "Canonical v1 accepts conversational text blocks, subject and response_requested only; identity and authority are server-owned.", {})
        return {"schema_version": 1, "content": [dict(item) for item in content],
            "subject": value.get("subject"), "intent": "conversation",
            "response_requested": value.get("response_requested", False)}
    if (not value or set(value) - {"text", "content"}
            or any(not isinstance(item, str) or not item for item in value.values())
            or len(value) == 2 and value["text"] != value["content"]):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                            "Use matching nonempty text/content strings or canonical v1 content blocks.", {})
    return {"text": next(iter(value.values()))}


class RuntimeControlService:
    def __init__(self, *, access, supervisor, owner_guard=None, commands=None, owner_identity=None, wake=None):
        self.access, self.supervisor = access, supervisor
        self.owner_guard = owner_guard
        self.commands, self.owner_identity, self.wake = commands, owner_identity, wake

    def _require_owner(self):
        if not self.owner_guard or not self.owner_guard():
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime effects require the active serve owner.", {})

    @contextmanager
    def _admission_uow(self, context, *, action, session_id):
        try:
            with self.access.cf.unit_of_work() as uow:
                yield uow
        except OktoNexusError:
            # The grant charge and intent roll back together. Record a denial
            # after rollback so a failed enqueue does not erase its audit.
            with self.access.cf.unit_of_work() as uow:
                endpoint_id = self.access.grants.runtime_endpoint(uow, session_id)
                self.access.grants.audit(uow, context=context, action=action, endpoint_id=endpoint_id,
                    session_id=session_id, grant=None, allowed=False, now=self.access.clock.now_iso())
            raise

    def send(self, context, *, session_id, verb, payload, idempotency_key=None,
             expected_operation_id=None, expected_turn_id=None, expected_owner_epoch=None):
        if verb not in {"send_turn", "steer", "interrupt", "close"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported runtime control.", {})
        action = "send" if verb == "send_turn" else verb
        # Authorize before validation so unauthorized callers get opaque errors.
        self.access.authorize(context, action=action, session_id=session_id, check_budget=False)
        payload = validate_runtime_payload(payload, required=verb in {"send_turn", "steer"})
        self._require_owner()
        if self.commands is None or self.owner_identity is None:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR, "Runtime commands require the durable serve composition.", {})
        if idempotency_key is not None and (not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Idempotency key must contain 1..128 characters.", {})
        if (any(value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 256)
                for value in (expected_operation_id, expected_turn_id)) or
                expected_owner_epoch is not None and (type(expected_owner_epoch) is not int or expected_owner_epoch < 1)):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid expected operation, turn or owner epoch.", {})
        key = idempotency_key or ("close:" + session_id if verb == "close" else new_id("command-key"))
        digest = self.commands.digest(session_id, verb, payload, expected_operation_id, expected_turn_id, expected_owner_epoch)
        actor_id = context.actor_agent_id or "operator"
        with self._admission_uow(context, action=action, session_id=session_id) as uow:
            self.access.authorize(context, action=action, session_id=session_id, uow=uow, check_budget=False)
            existing = self.commands.existing(uow, actor_id=actor_id, key=key)
            if existing:
                compatible_digests = {digest}
                if set(payload) == {"text"}:
                    # v2 persisted the legacy alias spelling in its digest.
                    # Preserve those immutable rows/replies across the upgrade.
                    compatible_digests.add(self.commands.digest(session_id, verb,
                        {"content": payload["text"]}, expected_operation_id, expected_turn_id, expected_owner_epoch))
                if existing["request_hash"] not in compatible_digests:
                    raise OktoNexusError(ErrorCode.CONFLICT, "Command key already binds different parameters.", {})
                return self.commands.response(existing)
            session = self.supervisor.get(session_id)
            if not session or session.owner_epoch != self.owner_identity[1]:
                raise OktoNexusError(ErrorCode.NOT_FOUND, "No current owned runtime for this command.", {})
            if verb != "close":
                self.supervisor._require_verb_allowed(session.capabilities, verb)
                validate_effective_control(session.compatibility_report, verb)
                validate_effective_capability(session.compatibility_report,
                    {"send_turn": "conversation", "steer": "steer_timing", "interrupt": "interrupt"}[verb])
            if expected_owner_epoch is not None and expected_owner_epoch != session.owner_epoch:
                raise OktoNexusError(ErrorCode.CONFLICT, "Command targets a different owner epoch.", {})
            target = self.supervisor.control_target(session_id) if verb in {"steer", "interrupt"} else None
            if verb in {"steer", "interrupt"}:
                if not target or not target.get("operation_id"):
                    raise OktoNexusError(ErrorCode.CONFLICT, "No correlated active turn for this control.", {})
                if (expected_operation_id is not None and expected_operation_id != target["operation_id"] or
                        expected_turn_id is not None and expected_turn_id != target["turn_id"]):
                    raise OktoNexusError(ErrorCode.CONFLICT, "Control targets a stale operation or native turn.", {})
            endpoint = self.access.endpoints.get(uow, session.endpoint_id)
            validate_declared_command(self.access.registry.get(endpoint["adapter_id"]).capabilities, verb)
            revision = self.access.endpoints.session_profile_revision(uow, session_id)
            grant = self.access.authorize(context, action=action, session_id=session_id, consume=True, uow=uow)
            row = self.commands.enqueue(uow, context=context, key=key, request_hash=digest, session=session,
                endpoint=endpoint, profile_revision=revision, verb=verb, payload=payload, grant=grant,
                expected_operation_id=target["operation_id"] if target else None,
                expected_turn_id=target["turn_id"] if target else None, now=self.access.clock.now_iso(),
                starts_turn=verb == "send_turn" or (verb == "steer" and target["steer_starts_new_turn"]))
        if self.wake:
            self.wake()
        return self.commands.response(row)

    def close(self, context, *, session_id, **kwargs):
        return self.send(context, session_id=session_id, verb="close", payload={}, **kwargs)

    def validate(self, uow, operation):
        if operation.get("reconciliation_id"):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime command was administratively reconciled.", {})
        context = RuntimeRequestContext(**json.loads(operation["context"]))
        if operation["grant_id"]:
            context = replace(context, execution_grant_id=operation["grant_id"])
        action = "send" if operation["verb"] == "send_turn" else operation["verb"]
        grant = self.access.authorize(context, action=action, session_id=operation["runtime_session_id"],
            uow=uow, check_budget=False)
        endpoint = self.access.endpoints.get(uow, operation["endpoint_id"])
        if (not endpoint or endpoint["revision"] != operation["endpoint_revision"] or
                self.owner_identity[1] != operation["expected_owner_epoch"] or
                (operation["grant_id"] and (not grant or grant["revision"] != operation["grant_revision"]))):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Command authority or binding changed before dispatch.", {})
        session = self.supervisor.get(operation["runtime_session_id"])
        validate_declared_command(self.access.registry.get(endpoint["adapter_id"]).capabilities, operation["verb"])
        if not session or session.owner_epoch != operation["expected_owner_epoch"]:
            raise OktoNexusError(ErrorCode.CONFLICT, "Command session is no longer owned.", {})
        validate_effective_control(session.compatibility_report, operation["verb"])
        if operation["verb"] != "close":
            validate_effective_capability(session.compatibility_report,
                {"send_turn": "conversation", "steer": "steer_timing", "interrupt": "interrupt"}[operation["verb"]])

    def execute(self, operation):
        self._require_owner()
        session_id = operation["runtime_session_id"]
        if operation["verb"] == "close":
            session = self.supervisor.close(session_id)
            return {"session_id": session_id, "status": session.status, "lifecycle_state": session.lifecycle_state,
                "metadata": dict(session.metadata)}
        payload = json.loads(operation["payload"])
        if payload.get("schema_version") == 1:
            session = self.supervisor.get(session_id)
            envelope = DeliveryEnvelope(operation_id=operation["operation_id"],
                sender_agent_id=operation["actor_agent_id"], recipient_agent_id=session.owning_agent_id,
                workspace_id=session.workspace_id, root_operation_id=operation["operation_id"],
                intent="conversation" if operation["verb"] == "send_turn" else "runtime_control",
                content=tuple(payload["content"]), subject=payload["subject"],
                response_requested=payload["response_requested"])
            payload = {"envelope": envelope.to_dict()}
        self.supervisor.send(session_id, operation["verb"], payload,
            _transport_attempt={"operation_id": operation["operation_id"], "attempt_id": operation["attempt_id"],
                "owner_epoch": operation["owner_epoch"], "expected_operation_id": operation["expected_operation_id"],
                "expected_turn_id": operation["expected_turn_id"]})
        return None

    def get_operation(self, context, *, operation_id):
        with self.access.cf.unit_of_work(write=False) as uow:
            row = self.commands.get(uow, operation_id)
            delivery = uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id=?", (operation_id,)).fetchone() if not row else None
        if delivery:
            self.access.authorize(context, action="read", endpoint_id=delivery["endpoint_id"])
            with self.access.cf.unit_of_work(write=False) as uow:
                result = uow.connection.execute("SELECT result_id,output_text,output_truncated,publication_state,delivery_outcome,relay_state,relay_reason FROM runtime_results "
                    "WHERE operation_id=? ORDER BY captured_at DESC LIMIT 1", (operation_id,)).fetchone()
                binding = uow.connection.execute("SELECT handoff_id,claim_epoch FROM runtime_handoff_bindings WHERE operation_id=?", (operation_id,)).fetchone()
                external = uow.connection.execute("SELECT b.external_acked_at AS acknowledged_at,"
                    "b.external_completion_action AS completion_action,h.status AS handoff_status "
                    "FROM runtime_handoff_bindings b JOIN handoffs h USING(handoff_id) "
                    "WHERE b.operation_id=? AND b.external_session_id IS NOT NULL", (operation_id,)).fetchone()
                outcome = uow.connection.execute("SELECT state,reason,response FROM runtime_work_outcomes WHERE operation_id=?", (operation_id,)).fetchone()
            return {"operation_id": operation_id, "session_id": delivery["runtime_session_id"], "state": delivery["status"],
                "attempt_id": delivery["attempt_id"], "owner_epoch": delivery["owner_epoch"], "reconciliation_id": delivery["reconciliation_id"],
                "durable": True, "ack_level": delivery["ack_level"], "reason": delivery["reason"],
                "context_observations": self._context_observations(context, operation_id),
                "external_work": (dict(external, contract_version=1, completion_channel="authenticated_nexus_call",
                    completed_at=delivery["external_completed_at"]) if external else None),
                "external_acceptance": "observed" if delivery["ack_level"] in {"HARNESS_ACCEPTED", "AGENT_ACK"} else "not_observed",
                "result_durable": delivery["terminal_event_id"] is not None, "result": dict(result) if result else None,
                "handoff": dict(binding) if binding else None,
                "work_outcome": {"state": outcome["state"], "reason": outcome["reason"],
                    "response": json.loads(outcome["response"]) if outcome["response"] else None} if outcome else None}
        if not row:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime operation is unavailable.", {})
        self.access.authorize(context, action="read", session_id=row["runtime_session_id"])
        with self.access.cf.unit_of_work(write=False) as uow:
            result = uow.connection.execute("SELECT result_id,output_text,output_truncated,publication_state,delivery_outcome,relay_state,relay_reason FROM runtime_results "
                "WHERE command_operation_id=? ORDER BY captured_at DESC LIMIT 1", (operation_id,)).fetchone()
        return self.commands.response(row) | {"reason": row["reason"], "owner_epoch": row["owner_epoch"],
            "attempt_id": row["attempt_id"], "reconciliation_id": row["reconciliation_id"],
            "native_turn_id": row["native_turn_id"], "expected_operation_id": row["expected_operation_id"],
            "result_durable": row["terminal_event_id"] is not None,
            "result": dict(result) if result else json.loads(row["result"]) if row["result"] else None}

    def _context_observations(self, context, source_operation_id):
        with self.access.cf.unit_of_work(write=False) as uow:
            rows = uow.connection.execute("SELECT operation_id,endpoint_id,runtime_session_id,status,reason,"
                "owner_epoch,attempt_id FROM runtime_context_observations WHERE source_operation_id=? "
                "ORDER BY created_at,operation_id", (source_operation_id,)).fetchall()
            visible = []
            for row in rows:
                try:
                    self.access.authorize(context, action="read", endpoint_id=row["endpoint_id"], uow=uow, audit=False)
                except OktoNexusError:
                    continue
                visible.append(dict(row, durable=True, external_acceptance="not_observed",
                    execution_authority=False, result_durable=False))
            return visible

    def replay(self, context, *, session_id, after_sequence=0, limit=200):
        self.access.authorize(context, action="events", session_id=session_id)
        return self.supervisor.replay_events(session_id, after_sequence=after_sequence, limit=limit)
