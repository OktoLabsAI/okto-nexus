"""Infrastructure-independent rules for single-use resource pools.

No process, SQL, clock or transport is owned by these rules. Zero capacity means
no pool-specific ceiling; an execution host can still impose its own ceiling.
Starting and closing instances consume capacity until disposal is confirmed.
"""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PoolPolicy:
    max_parallel: int = 1
    warm_instances: int = 0
    overflow: str = 'queue'
    queue_capacity: int = 32
    queue_timeout_seconds: int = 300
    execution_timeout_seconds: int = 1800

    def to_dict(self):
        return asdict(self)

    def __post_init__(self):
        for name in ('max_parallel', 'warm_instances', 'queue_capacity'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f'Invalid {name}')
        for name in ('queue_timeout_seconds', 'execution_timeout_seconds'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f'Invalid {name}')
        if self.overflow not in ('queue', 'reject'):
            raise ValueError('Invalid overflow policy')
        if self.max_parallel and self.warm_instances >= self.max_parallel:
            raise ValueError('Warm target must be below the capacity ceiling')

    def room(self, *, occupied: int, host_occupied: int, host_limit: int) -> bool:
        if type(host_limit) is not int or host_limit < 0:
            raise ValueError('A nonnegative host capacity is required')
        return host_occupied < host_limit and (not self.max_parallel or occupied < self.max_parallel)

    def may_claim(self, *, occupied: int, host_occupied: int, host_limit: int) -> bool:
        if type(host_limit) is not int or host_limit < 0:
            raise ValueError('A nonnegative host capacity is required')
        return host_occupied <= host_limit and (not self.max_parallel or occupied <= self.max_parallel)


@dataclass(frozen=True)
class PoolRequest:
    request_id: str
    pool_id: str
    host_id: str
    caller_id: str
    request_hash: str
    configuration: str
    policy: PoolPolicy
    state: str
    enqueued_at: float
    queue_deadline: float
    started_at: float | None = None
    execution_deadline: float | None = None
    admission_deadline: float | None = None
    outcome: dict | None = None


@dataclass(frozen=True)
class PoolInstance:
    instance_id: str
    pool_id: str
    host_id: str
    configuration: str
    state: str
    created_at: float
    request_id: str | None = None
    resource_id: str | None = None


class PoolConflict(ValueError):
    """A caller identity or state transition conflicts with durable state."""


class PoolNotFound(LookupError):
    pass
