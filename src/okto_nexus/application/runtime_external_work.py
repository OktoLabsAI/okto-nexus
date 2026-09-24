"""External work proof v1, using canonical Nexus sessions and agent credentials.

Nothing here treats a native socket write as an acknowledgement. All methods
operate within the caller's existing transaction and perform no external I/O.
"""
from dataclasses import dataclass, replace
import hashlib
import hmac

from ..errors import ErrorCode, OktoNexusError
from .endpoints import EndpointService
from .identity import verify_session_credentials


def denied():
    return OktoNexusError(ErrorCode.PERMISSION_DENIED, "External Nexus work channel is not authorized.", {})


@dataclass(frozen=True)
class ExternalWorkProof:
    session_id: str
    secret_binding: str


class ExternalWorkChannel:
    def __init__(self, *, access, sessions):
        self.access, self.sessions = access, sessions

    def current(self, uow, *, context, endpoint, proof=None, session_id=None, session_secret=None):
        if (not context or context.authentication_source != "agent_key"
                or context.actor_agent_id != endpoint["agent_id"]
                or self.access.registry.get(endpoint["adapter_id"]).substrate != "attach"):
            raise denied()
        # Authentication remains mandatory for trusted persisted-proof replay.
        self.access.authenticate(context, uow=uow)
        try:
            EndpointService.validate_work_session_reference(uow, public_config=endpoint["public_config"],
                agent_id=endpoint["agent_id"], workspace_id=endpoint["workspace_id"])
            selected = endpoint["public_config"].get("nexus_work_session_id")
            if not selected or selected != (proof.session_id if proof else session_id):
                raise denied()
            if proof is None:
                verify_session_credentials(self.sessions, uow, trust_mode="strict", tool="external_work",
                    agent_id=context.actor_agent_id, session_id=session_id, session_secret=session_secret)
            stored = self.sessions.get_secret(uow, session_id=selected)
            if not stored:
                raise denied()
            fingerprint = hashlib.sha256(stored.encode()).hexdigest()
            if proof and not hmac.compare_digest(proof.secret_binding, fingerprint):
                raise denied()
        except OktoNexusError:
            raise denied() from None
        return ExternalWorkProof(selected, fingerprint)

    def returning(self, uow, *, context, operation, binding, agent_id, session_id, session_secret,
                  claim_epoch=None, require_ack=False, repeated_ack=False):
        if (not context or context.actor_agent_id != agent_id
                or operation["recipient_agent_id"] != agent_id
                or operation["actor_agent_id"] != agent_id
                or operation["credential_binding"] != context.credential_binding
                or operation["reconciliation_id"] is not None
                or claim_epoch is not None and claim_epoch != binding["claim_epoch"]):
            raise denied()
        endpoint = self.access.endpoints.get(uow, operation["endpoint_id"])
        if not endpoint or endpoint["revision"] != operation["endpoint_revision"]:
            raise denied()
        proof = self.current(uow, context=context, endpoint=endpoint,
            session_id=session_id, session_secret=session_secret)
        if proof != ExternalWorkProof(binding["external_session_id"], binding["external_secret_binding"]):
            raise denied()
        grant = self.access.authorize(replace(context, execution_grant_id=binding["grant_id"]),
            action="execute_work", endpoint_id=endpoint["endpoint_id"], represented_agent_id=agent_id,
            workspace_id=operation["workspace_id"], check_budget=False, uow=uow,
            _returning_external_work=True)
        if not grant or grant["revision"] != binding["grant_revision"]:
            raise denied()
        handoff = uow.connection.execute("SELECT status,claimed_by,claim_epoch FROM handoffs WHERE handoff_id=?",
            (binding["handoff_id"],)).fetchone()
        already_finished = (repeated_ack and binding["external_acked_at"] and operation["external_completed_at"]
            and handoff and handoff["status"] in {"VERIFYING", "COMPLETED", "REJECTED"})
        if (not handoff or handoff["claimed_by"] != agent_id or handoff["claim_epoch"] != binding["claim_epoch"]
                or handoff["status"] != "CLAIMED" and not already_finished
                or require_ack and not binding["external_acked_at"]):
            raise denied()
        if operation["status"] not in {"SENDING", "SENT_UNCONFIRMED", "ACCEPTED", "OUTCOME_UNKNOWN"}:
            raise denied()
        return proof
