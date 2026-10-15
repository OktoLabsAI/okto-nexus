"""Internal, task-scoped automation authority; not an inbound credential."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HandoffAutomationPrincipal:
    agent_id: str
    workspace_id: str
    endpoint_id: str
    handoff_id: str
    attempt_id: str
    grant_id: str
    grant_revision: int
    policy_digest: str
    agent_digest: str

    def __post_init__(self):
        for name in ('agent_id', 'workspace_id', 'endpoint_id', 'handoff_id', 'attempt_id',
                     'grant_id', 'policy_digest', 'agent_digest'):
            value = getattr(self, name)
            if type(value) is not str or not 1 <= len(value) <= 256 or not value.isprintable():
                raise ValueError('Invalid handoff automation scope.')
        if type(self.grant_revision) is not int or self.grant_revision < 1:
            raise ValueError('Invalid handoff automation grant revision.')
