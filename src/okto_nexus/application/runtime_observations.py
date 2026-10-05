"""Nonexecuting context uses the same owner, canonical audience and inbox source."""
import json

from ..errors import ErrorCode, OktoNexusError
from .runtime_requirements import validate_effective_capability


class RuntimeObservationService:
    def __init__(self, *, owner, planner, messages, supervisor):
        self.owner, self.planner, self.messages, self.supervisor = owner, planner, messages, supervisor
        self.owner_identity = None

    def validate(self, uow, operation):
        source = self.owner.repo.get(uow, operation["source_operation_id"])
        if not source or source["reconciliation_id"] or source["status"] in {"REJECTED", "CANCELLED", "FAILED_FINAL"}:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Observation source is unavailable.", {})
        # Reuse canonical delivery policy, actor credential and audience checks.
        self.planner.revalidate(uow, operation=source, config=self.planner.config)
        self.messages.revalidate_runtime_delivery(uow, source)
        endpoint = self.planner.endpoints.get(uow, operation["endpoint_id"])
        eligible = self.planner.observer_candidates(uow, agent_id=source["recipient_agent_id"], workspace_id=source["workspace_id"])
        match = next((item for item in eligible if item[0]["endpoint_id"] == operation["endpoint_id"]
            and item[2]["session_id"] == operation["runtime_session_id"]), None)
        if (not match or endpoint["revision"] != operation["endpoint_revision"]
                or (match[1]["revision"] if match[1] else None) != operation["profile_revision"]
                or match[2]["owner_epoch"] != operation["expected_owner_epoch"]
                or operation["expected_owner_epoch"] != self.owner.epoch):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Observation binding changed.", {})

    def execute(self, operation):
        with self.owner.cf.unit_of_work(write=False) as uow:
            self.validate(uow, operation)
            if not self.owner.repo.owns(uow, owner_id=self.owner.owner_id, epoch=self.owner.epoch,
                    now=self.owner.clock.now_iso()):
                raise OktoNexusError(ErrorCode.CONFLICT, "Observation owner changed.", {})
        session = self.supervisor.get(operation["runtime_session_id"])
        validate_effective_capability(session.compatibility_report, "context_without_execution")
        self.supervisor.observe_context(operation["runtime_session_id"], json.loads(operation["envelope"]))
