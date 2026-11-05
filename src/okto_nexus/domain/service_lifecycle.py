"""Service identity/readiness facts, independent of agent identity and execution."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

SERVICE_PROTOCOL_REVISION = 1


def instance_id(*, component: str, home: str, database: str, principal: str) -> str:
    """Inputs are canonical host-resolved references, never credentials."""
    if component not in {'server', 'connector'} or not home or not principal:
        raise ValueError('Invalid service instance identity')
    data = json.dumps([component, home, database, principal], ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')
    return 'svc_' + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ServiceReadiness:
    component: str
    instance_id: str
    generation: str
    active_version: str
    pid: int
    supervisor: str
    state: str
    ready_for_queries: bool
    storage_initialized: bool
    admission: str
    reason: str | None
    next_action: str | None
    protocol_revision: int = SERVICE_PROTOCOL_REVISION

    def to_dict(self) -> dict:
        return asdict(self)
