"""One transport intent per canonical handoff claim; no separate work queue."""
from dataclasses import replace
import hashlib
import json

from ..domain.base import new_id
from ..domain.delivery import DeliveryEnvelope
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .runtime_bootstrap import delivery_context
from .runtime_causality import RuntimeCausalityService
from .runtime_requirements import validate_effective_capability


def denied():
    return OktoNexusError(ErrorCode.PERMISSION_DENIED, "Managed handoff execution is not authorized.", {})


class RuntimeWorkService:
    def __init__(self, *, access, outbox, messages, deliveries, clock, validate_claim, wake, owner_provider=None):
        self.access, self.outbox = access, outbox
        self.messages, self.deliveries, self.clock = messages, deliveries, clock
        self.validate_claim, self.wake = validate_claim, wake
        self.owner_provider = owner_provider

    def authorize(self, uow, *, context, endpoint_id, grant_id, agent_id, workspace_id, consume=False, audit=True):
        if not context or not grant_id or not endpoint_id:
            raise denied()
        context = replace(context, execution_grant_id=grant_id)
        grant = self.access.authorize(context, action="execute_work", endpoint_id=endpoint_id,
            represented_agent_id=agent_id, workspace_id=workspace_id, consume=consume,
            check_budget=consume, uow=uow, audit=audit)
        if not grant:
            raise denied()
        endpoint = self.access.endpoints.get(uow, endpoint_id)
        descriptor = self.access.registry.get(endpoint["adapter_id"])
        # Attach has no authenticated work completion channel in this version.
        # Events alone are not a work grant; a selected approved native profile
        # and explicit caller delegation are both required.
        if not descriptor.capabilities.managed_work or not descriptor.capabilities.events or endpoint["consumption"] != "exclusive" or not endpoint["profile_id"]:
            raise denied()
        profile = self.access.endpoints.profile(uow, endpoint["profile_id"])
        if profile and "managed_work" in profile["config"].get("disabled_capabilities", ()):
            raise denied()
        return context, grant, endpoint, profile

    @staticmethod
    def request_hash(*, handoff_id, agent_id, endpoint_id, grant_id, claim_epoch, idempotency_key,
                     completion_mode="authenticated_nexus_call"):
        if not isinstance(completion_mode, str) or completion_mode not in {"authenticated_nexus_call", "structured_result_v1"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported work completion contract.", {})
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Managed claim requires an idempotency_key of 1..128 characters.", {})
        if claim_epoch is not None and (type(claim_epoch) is not int or claim_epoch < 1):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "claim_epoch must be a positive integer.", {})
        identity = [handoff_id, agent_id, endpoint_id, grant_id, claim_epoch]
        if completion_mode != "authenticated_nexus_call":
            identity.append(completion_mode)
        return hashlib.sha256(json.dumps(identity,
                                       separators=(",", ":")).encode()).hexdigest()

    def existing(self, uow, *, context, key, digest):
        row = uow.connection.execute("SELECT b.*,o.status,o.endpoint_id,o.credential_binding FROM runtime_handoff_bindings b "
            "JOIN delivery_outbox o ON o.operation_id=b.operation_id WHERE b.actor_agent_id=? AND b.idempotency_key=?",
            (context.actor_agent_id, key)).fetchone()
        if row and (row["request_hash"] != digest or row["credential_binding"] != context.credential_binding):
            raise OktoNexusError(ErrorCode.CONFLICT, "Managed claim key already identifies another request.", {})
        return dict(row) if row else None

    def enqueue(self, uow, *, handoff, authorized, key, digest, now, completion_mode="authenticated_nexus_call"):
        context, grant, endpoint, profile = authorized
        if uow.connection.execute("SELECT 1 FROM runtime_handoff_bindings WHERE handoff_id=? AND claim_epoch=?",
                (handoff.handoff_id, handoff.claim_epoch)).fetchone():
            raise OktoNexusError(ErrorCode.CONFLICT, "This claim already has a managed execution; use its original request key.", {})
        revision = self.validate_claim(uow, handoff=handoff)
        active = uow.connection.execute("SELECT count(*),COALESCE(sum(recipient_agent_id=?),0),"
            "COALESCE(sum(workspace_id=?),0) FROM delivery_outbox WHERE status IN ('PENDING','CLAIMED','SENDING','OUTCOME_UNKNOWN') "
            "OR (status IN ('ACCEPTED','SENT_UNCONFIRMED') AND terminal_event_id IS NULL)",
            (handoff.claimed_by, handoff.workspace_id)).fetchone()
        if any(count >= limit for count, limit in zip(active, (256, 32, 128))):
            raise OktoNexusError(ErrorCode.QUOTA_EXCEEDED, "Managed delivery capacity is exhausted.", {})
        self.authorize(uow, context=context, endpoint_id=endpoint["endpoint_id"], grant_id=grant["grant_id"],
                       agent_id=handoff.claimed_by, workspace_id=handoff.workspace_id, consume=True)
        message = self.messages.create(uow, message_id=new_id("msg"), workspace_id=handoff.workspace_id,
            from_agent_id=handoff.from_agent_id, target=json.dumps({"strategy": "direct", "agent_id": handoff.claimed_by}),
            subject="Managed handoff execution", body=handoff.payload or "", trace_id=handoff.trace_id, created_at=now)
        causality = RuntimeCausalityService(config=self.access.config, agents=self.access.agents)
        # Original creator provenance was checked by validate_claim; the
        # authenticated claimant/delegate is the actor admitting this execution.
        causality.record(uow, message=message, context=context, now=now, authorized_work=True)
        cause = causality.reserve_execution(uow, message_id=message.message_id, now=now)
        delivery = self.deliveries.create(uow, delivery_id=new_id("del"), message_id=message.message_id,
            recipient_agent_id=handoff.claimed_by, status="unread", created_at=now)
        operation_id = new_id("op")
        bootstrap = delivery_context(uow, agents=self.access.agents, endpoint=endpoint,
                                     profile=profile, intent="handoff_execute")
        bootstrap["causality"] = causality.context(cause)
        if completion_mode == "structured_result_v1":
            bootstrap["completion"] = {"automatic_on_turn_end": False, "mode": completion_mode,
                "required_response": {"nexus_work_result": {"schema_version": 1,
                    "operation_id": operation_id, "handoff_id": handoff.handoff_id,
                    "claim_epoch": handoff.claim_epoch, "action": "complete", "result": "Your explicit result/evidence"}},
                "reject_alternative": {"action": "reject", "reason": "Your explicit reason"}}
            bootstrap["instructions"] += (
                " This dispatch explicitly permits structured_result_v1 instead of a tool call: return exactly one JSON object "
                "matching required_response, without markdown or surrounding prose. To reject, replace action/result with "
                "action/reason from reject_alternative. Preserve all correlation fields. Do not verify your own work.")
        envelope = DeliveryEnvelope(operation_id, handoff.from_agent_id, handoff.claimed_by, handoff.workspace_id,
            "handoff_execute", ({"type": "text", "text": handoff.payload or ""},), cause["root_operation_id"],
            message_id=message.message_id, delivery_id=delivery.delivery_id, context_id=handoff.handoff_id,
            subject=message.subject, handoff_id=handoff.handoff_id, claim_epoch=handoff.claim_epoch,
            runtime_context=bootstrap)
        live = self.outbox.live_sessions(uow, endpoint_id=endpoint["endpoint_id"])
        if len(live) > 1:
            raise OktoNexusError(ErrorCode.CONFLICT, "AMBIGUOUS_BINDING", {})
        if live:
            validate_effective_capability(live[0]["compatibility_report"], "managed_work")
        self.outbox.enqueue(uow, envelope=envelope, context=context, endpoint=endpoint, profile=profile,
                            session_id=live[0]["session_id"] if live else None, now=now, authorization_revision=revision)
        uow.connection.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,"
            "actor_agent_id,idempotency_key,request_hash,created_at,completion_mode) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (handoff.handoff_id, handoff.claim_epoch, operation_id, grant["grant_id"], grant["revision"],
             context.actor_agent_id, key, digest, now, completion_mode))
        return dict(operation_id=operation_id, claim_epoch=handoff.claim_epoch, status="PENDING", grant_id=grant["grant_id"])

    def revalidate(self, uow, *, operation):
        if operation.get("reconciliation_id"):
            raise denied()
        binding = uow.connection.execute("SELECT * FROM runtime_handoff_bindings WHERE operation_id=?",
                                         (operation["operation_id"],)).fetchone()
        if not binding:
            raise denied()
        handoff = uow.connection.execute("SELECT status,claimed_by,claim_epoch FROM handoffs WHERE handoff_id=?",
                                        (binding["handoff_id"],)).fetchone()
        if not handoff or handoff["status"] != "CLAIMED" or handoff["claimed_by"] != operation["recipient_agent_id"] or handoff["claim_epoch"] != binding["claim_epoch"]:
            raise denied()
        context = RuntimeRequestContext(operation["actor_agent_id"], "agent_key", credential_binding=operation["credential_binding"])
        _, grant, endpoint, profile = self.authorize(uow, context=context, endpoint_id=operation["endpoint_id"],
            grant_id=binding["grant_id"], agent_id=operation["recipient_agent_id"], workspace_id=operation["workspace_id"], audit=False)
        if (grant["revision"] != binding["grant_revision"] or endpoint["revision"] != operation["endpoint_revision"]
                or profile["revision"] != operation["profile_revision"]):
            raise denied()
        if operation["runtime_session_id"] and self.access.endpoints.session_profile_revision(uow, operation["runtime_session_id"]) != profile["revision"]:
            raise denied()
        if operation["runtime_session_id"]:
            row = uow.connection.execute("SELECT compatibility_report FROM harness_sessions WHERE session_id=?",
                (operation["runtime_session_id"],)).fetchone()
            validate_effective_capability(json.loads(row[0]) if row else {}, "managed_work")
        if self.validate_claim(uow, handoff_id=binding["handoff_id"], workspace_id=operation["workspace_id"]) != operation["authorization_revision"]:
            raise denied()
        return endpoint, profile

    def result_decision(self, uow, result_id):
        """Parse only an explicitly admitted contract on an exact durable result."""
        row = uow.connection.execute(
            "SELECT r.*,b.handoff_id,b.claim_epoch,b.completion_mode,o.terminal_event_id,"
            "o.recipient_agent_id,o.workspace_id,w.root_realpath FROM runtime_results r "
            "JOIN delivery_outbox o ON o.operation_id=r.operation_id "
            "JOIN runtime_handoff_bindings b ON b.operation_id=o.operation_id "
            "JOIN workspaces w ON w.workspace_id=o.workspace_id WHERE r.result_id=?", (result_id,)).fetchone()
        if (not row or row["completion_mode"] != "structured_result_v1" or
                row["event_id"] != row["terminal_event_id"] or row["output_truncated"]):
            raise denied()
        try:
            def unique_pairs(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError("Duplicate structured decision field")
                    value[key] = item
                return value
            decoded = json.loads(row["output_text"], object_pairs_hook=unique_pairs,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        except (ValueError, TypeError, RecursionError):
            return None
        if not isinstance(decoded, dict) or set(decoded) != {"nexus_work_result"}:
            return None
        decision = decoded["nexus_work_result"]
        if not isinstance(decision, dict):
            raise denied()
        action = decision.get("action")
        field = "result" if action == "complete" else "reason"
        if (action not in {"complete", "reject"} or
                set(decision) != {"schema_version", "operation_id", "handoff_id", "claim_epoch", "action", field} or
                type(decision["schema_version"]) is not int or decision["schema_version"] != 1 or
                type(decision["claim_epoch"]) is not int or decision["claim_epoch"] != row["claim_epoch"] or
                decision["operation_id"] != row["operation_id"] or decision["handoff_id"] != row["handoff_id"] or
                decision[field] in (None, "", {}, [])):
            raise denied()
        return {"project_root": row["root_realpath"], "handoff_id": row["handoff_id"],
                "agent_id": row["recipient_agent_id"], "claim_epoch": row["claim_epoch"],
                field: decision[field]}, action, dict(row)

    def require_result_owner(self, uow):
        owner = self.owner_provider() if self.owner_provider else None
        if (not owner or owner._stop.is_set() or
                not owner.repo.owns(uow, owner_id=owner.owner_id, epoch=owner.epoch, now=self.clock.now_iso())):
            raise OktoNexusError(ErrorCode.CONFLICT, "Result projection requires the current runtime owner.", {})

    def authorize_result(self, uow, *, result_id, action, supplied):
        self.require_result_owner(uow)
        parsed = self.result_decision(uow, result_id)
        if not parsed or parsed[1] != action or parsed[0] != supplied:
            raise denied()
        row = parsed[2]
        existing = uow.connection.execute("SELECT state,response FROM runtime_work_outcomes WHERE result_id=?", (result_id,)).fetchone()
        if existing:
            if existing["state"] != "APPLIED":
                raise denied()
            return json.loads(existing["response"])
        operation = self.outbox.get(uow, row["operation_id"])
        self.revalidate(uow, operation=operation)
        return None

    def record_result(self, uow, *, result_id, state, response=None, reason=None):
        self.require_result_owner(uow)
        uow.connection.execute("INSERT INTO runtime_work_outcomes(result_id,operation_id,state,response,reason,created_at) "
            "SELECT result_id,operation_id,?,?,?,? FROM runtime_results WHERE result_id=? "
            "ON CONFLICT(result_id) DO NOTHING",
            (state, json.dumps(response, ensure_ascii=False) if response is not None else None,
             reason, self.clock.now_iso(), result_id))
        if state == "APPLIED":
            # The canonical handoff transition already owns result disclosure
            # and verifier/creator notification. Do not publish the control JSON
            # again as conversation, or mislabel a completed transition denied.
            uow.connection.execute("UPDATE runtime_results SET publication_state='WORK_APPLIED',"
                "publication_reason='canonical_handoff_outcome' WHERE result_id=? "
                "AND publication_state='PENDING_AUTHORIZATION'", (result_id,))

    @staticmethod
    def owns_claim(uow, *, handoff_id):
        # Even a terminal native turn is not complete/reject/verify. Keep the
        # canonical claimant until an explicit canonical transition; a lease
        # expiration must not hand uncertain or accepted work to another agent.
        return uow.connection.execute("SELECT 1 FROM runtime_handoff_bindings b "
                                      "JOIN handoffs h ON h.handoff_id=b.handoff_id AND h.claim_epoch=b.claim_epoch "
                                      "JOIN delivery_outbox o ON o.operation_id=b.operation_id "
                                      "WHERE b.handoff_id=? AND o.reconciliation_id IS NULL LIMIT 1",
                                      (handoff_id,)).fetchone() is not None

    @staticmethod
    def binding(uow, *, handoff_id, claim_epoch):
        row = uow.connection.execute("SELECT b.operation_id,b.claim_epoch,b.grant_id,b.completion_mode,o.status,o.ack_level,o.reason,"
            "o.runtime_session_id,o.terminal_event_id FROM runtime_handoff_bindings b "
            "JOIN delivery_outbox o ON o.operation_id=b.operation_id WHERE b.handoff_id=? AND b.claim_epoch=?",
            (handoff_id, claim_epoch)).fetchone()
        return dict(row) if row else None
