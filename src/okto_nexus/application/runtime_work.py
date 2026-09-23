"""One transport intent per canonical handoff claim; no separate work queue."""
from dataclasses import replace
import hashlib
import json

from ..domain.base import new_id
from ..domain.delivery import DeliveryEnvelope
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError


def denied():
    return OktoNexusError(ErrorCode.PERMISSION_DENIED, "Managed handoff execution is not authorized.", {})


class RuntimeWorkService:
    def __init__(self, *, access, outbox, messages, deliveries, clock, validate_claim, wake):
        self.access, self.outbox = access, outbox
        self.messages, self.deliveries, self.clock = messages, deliveries, clock
        self.validate_claim, self.wake = validate_claim, wake

    def authorize(self, uow, *, context, endpoint_id, grant_id, agent_id, workspace_id, consume=False):
        if not context or not grant_id or not endpoint_id:
            raise denied()
        context = replace(context, execution_grant_id=grant_id)
        grant = self.access.authorize(context, action="execute_work", endpoint_id=endpoint_id,
            represented_agent_id=agent_id, workspace_id=workspace_id, consume=consume,
            check_budget=consume, uow=uow)
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
        return context, grant, endpoint, profile

    @staticmethod
    def request_hash(*, handoff_id, agent_id, endpoint_id, grant_id, claim_epoch, idempotency_key):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Managed claim requires an idempotency_key of 1..128 characters.", {})
        if claim_epoch is not None and (type(claim_epoch) is not int or claim_epoch < 1):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "claim_epoch must be a positive integer.", {})
        return hashlib.sha256(json.dumps([handoff_id, agent_id, endpoint_id, grant_id, claim_epoch],
                                       separators=(",", ":")).encode()).hexdigest()

    def existing(self, uow, *, context, key, digest):
        row = uow.connection.execute("SELECT b.*,o.status,o.endpoint_id,o.credential_binding FROM runtime_handoff_bindings b "
            "JOIN delivery_outbox o ON o.operation_id=b.operation_id WHERE b.actor_agent_id=? AND b.idempotency_key=?",
            (context.actor_agent_id, key)).fetchone()
        if row and (row["request_hash"] != digest or row["credential_binding"] != context.credential_binding):
            raise OktoNexusError(ErrorCode.CONFLICT, "Managed claim key already identifies another request.", {})
        return dict(row) if row else None

    def enqueue(self, uow, *, handoff, authorized, key, digest, now):
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
        delivery = self.deliveries.create(uow, delivery_id=new_id("del"), message_id=message.message_id,
            recipient_agent_id=handoff.claimed_by, status="unread", created_at=now)
        operation_id = new_id("op")
        envelope = DeliveryEnvelope(operation_id, handoff.from_agent_id, handoff.claimed_by, handoff.workspace_id,
            "handoff_execute", ({"type": "text", "text": handoff.payload or ""},), operation_id,
            message_id=message.message_id, delivery_id=delivery.delivery_id, context_id=handoff.handoff_id,
            subject=message.subject, handoff_id=handoff.handoff_id, claim_epoch=handoff.claim_epoch)
        live = self.outbox.live_sessions(uow, endpoint_id=endpoint["endpoint_id"])
        if len(live) > 1:
            raise OktoNexusError(ErrorCode.CONFLICT, "AMBIGUOUS_BINDING", {})
        self.outbox.enqueue(uow, envelope=envelope, context=context, endpoint=endpoint, profile=profile,
                            session_id=live[0]["session_id"] if live else None, now=now, authorization_revision=revision)
        uow.connection.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,"
            "actor_agent_id,idempotency_key,request_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (handoff.handoff_id, handoff.claim_epoch, operation_id, grant["grant_id"], grant["revision"],
             context.actor_agent_id, key, digest, now))
        return dict(operation_id=operation_id, claim_epoch=handoff.claim_epoch, status="PENDING", grant_id=grant["grant_id"])

    def revalidate(self, uow, *, operation):
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
            grant_id=binding["grant_id"], agent_id=operation["recipient_agent_id"], workspace_id=operation["workspace_id"])
        if (grant["revision"] != binding["grant_revision"] or endpoint["revision"] != operation["endpoint_revision"]
                or profile["revision"] != operation["profile_revision"]):
            raise denied()
        if operation["runtime_session_id"] and self.access.endpoints.session_profile_revision(uow, operation["runtime_session_id"]) != profile["revision"]:
            raise denied()
        if self.validate_claim(uow, handoff_id=binding["handoff_id"], workspace_id=operation["workspace_id"]) != operation["authorization_revision"]:
            raise denied()
        return endpoint, profile

    @staticmethod
    def owns_claim(uow, *, handoff_id):
        # Even a terminal native turn is not complete/reject/verify. Keep the
        # canonical claimant until an explicit canonical transition; a lease
        # expiration must not hand uncertain or accepted work to another agent.
        return uow.connection.execute("SELECT 1 FROM runtime_handoff_bindings WHERE handoff_id=? LIMIT 1",
                                      (handoff_id,)).fetchone() is not None

    @staticmethod
    def binding(uow, *, handoff_id, claim_epoch):
        row = uow.connection.execute("SELECT b.operation_id,b.claim_epoch,b.grant_id,o.status,o.ack_level,o.reason,"
            "o.runtime_session_id,o.terminal_event_id FROM runtime_handoff_bindings b "
            "JOIN delivery_outbox o ON o.operation_id=b.operation_id WHERE b.handoff_id=? AND b.claim_epoch=?",
            (handoff_id, claim_epoch)).fetchone()
        return dict(row) if row else None
