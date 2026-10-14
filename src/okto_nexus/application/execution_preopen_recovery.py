"""Accept positive preopening fences through the authenticated recovery owner."""
from typing import Protocol
from dataclasses import dataclass

from nexus_connector_core.preopen_refusal_r4 import validate_r4_preopen_report


class PreopenRecoveryRepository(Protocol):
    def accept(self, uow, channel, report) -> set[str]: ...
    def receipt_high(self, uow, channel, *, agent_id=None) -> int: ...


@dataclass(frozen=True)
class PreopenRecoveryAccepted:
    retired_operations: frozenset[str]
    receipt_high_before: int
    receipt_high_after: int


class ExecutionPreopenRecovery:
    def __init__(self, repository: PreopenRecoveryRepository):
        self.repository = repository

    def accept(self, uow, channel, reports, *, agent_id=None):
        if type(reports) is not list or len(reports) > 128:
            raise ValueError('Invalid preopening recovery page.')
        seen, retired = set(), set()
        before = self.repository.receipt_high(uow, channel, agent_id=agent_id)
        for report in reports:
            report = validate_r4_preopen_report(report)
            source = report['refusal']['source']
            if (source['operation_id'] in seen
                    or (source['server_id'], source['executor_id']) != (channel.server_id, channel.executor_id)
                    or agent_id is not None and source['agent_id'] != agent_id
                    or source['connection_generation'] >= channel.connection_generation):
                raise ValueError('The preopening recovery owner or operation is invalid.')
            seen.add(source['operation_id'])
            retired.update(self.repository.accept(uow, channel, report))
        return PreopenRecoveryAccepted(frozenset(retired), before,
            self.repository.receipt_high(uow, channel, agent_id=agent_id))
