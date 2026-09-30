"""Operator proofs for immutable R4 binding proposals, without native effects."""

from datetime import datetime, timezone
import json

from ..errors import ErrorCode, OktoNexusError


BINDING_APPROVAL_ACTION = "execution.binding.authorize"


class ExecutionBindingApprovals:
    def __init__(self, *, access):
        self.access = access

    def decide(self, uow, approval, *, approved, response, context, decided_by, replay):
        from nexus_connector_core.protocol import canonical_json
        from .execution_binding_proposals import _agent_guard, _require_binding_method

        if (context is None or decided_by != (context.actor_agent_id or "operator") or
                not self.access.authenticate(context, uow=uow, require_feature=False)):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "An authenticated operator must decide this binding proposal.", {})
        if response is not None:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                  "Binding approval does not accept input data.", {})
        if replay:
            return json.loads(approval.executed_result) if approval.executed_result else None
        conn = uow.connection
        request = json.loads(approval.request_payload)["kwargs"]
        row = conn.execute(
            "SELECT * FROM execution_proposals WHERE proposal_id=? AND server_id=? "
            "AND subject_agent_id=?",
            (request["proposal_id"], request["server_id"], approval.agent_id),
        ).fetchone()
        if row is None:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The binding proposal is unavailable.", {})
        expected = json.loads(row["expected_revisions_json"])
        proposal = json.loads(row["proposal_json"])
        if (expected.get("operator_approval_id") != approval.approval_id or
                row["diff_hash"] != request["approved_diff_hash"] or
                row["proposal_revision"] != request["proposal_revision"] or
                proposal["workspace_id"] != approval.workspace_id):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The approval does not match the binding proposal.", {})
        result = {"proposal_id": row["proposal_id"],
                  "operator_proof_ref": approval.approval_id if approved else None}
        if not approved:
            return result
        self.access.authorize(context, uow=uow, audit=False)
        if (row["status"] != "PREPARED" or not proposal["can_apply"] or
                datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc) or
                _agent_guard(conn, row["subject_agent_id"]) != expected["agent_guard_digest"]):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The binding proposal expired or its policy changed.", {})
        _require_binding_method(conn, subject_agent_id=row["subject_agent_id"],
                                adapter_id=proposal["adapter_id"])
        proof = {"approval_id": approval.approval_id,
                 "proposal_id": row["proposal_id"],
                 "proposal_revision": row["proposal_revision"],
                 "approved_diff_hash": row["diff_hash"],
                 "operator_agent_id": decided_by,
                 "operator_guard_digest": _agent_guard(conn, decided_by)}
        conn.execute("UPDATE execution_proposals SET operator_proof_json=? WHERE proposal_id=?",
                     (canonical_json(proof).decode("utf-8"), row["proposal_id"]))
        return result


def verify_binding_operator_proof(conn, *, proposal_row, expected, proof_ref):
    """Compare a stored proof with its committed decision and current operator."""
    from .execution_binding_proposals import _agent_guard

    if (not proof_ref or proof_ref != expected.get("operator_approval_id") or
            not proposal_row["operator_proof_json"]):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "The binding requires an approved operator proof.", {})
    proof = json.loads(proposal_row["operator_proof_json"])
    approval = conn.execute("SELECT * FROM approvals WHERE approval_id=?", (proof_ref,)).fetchone()
    if (approval is None or approval["status"] != "approved" or
            approval["action"] != BINDING_APPROVAL_ACTION or
            approval["agent_id"] != proposal_row["subject_agent_id"] or
            approval["decided_by"] != proof["operator_agent_id"] or
            proof["approval_id"] != proof_ref or
            proof["proposal_id"] != proposal_row["proposal_id"] or
            proof["proposal_revision"] != proposal_row["proposal_revision"] or
            proof["approved_diff_hash"] != proposal_row["diff_hash"] or
            _agent_guard(conn, proof["operator_agent_id"]) != proof["operator_guard_digest"]):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "The binding operator proof is no longer valid.", {})
