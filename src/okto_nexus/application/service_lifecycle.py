"""Read-only lifecycle projection. Runtime authority remains in existing gates."""
from __future__ import annotations

from ..domain.service_lifecycle import ServiceReadiness


def project_server_readiness(*, identity: str, generation: str, version: str,
                             pid: int, owns_instance: bool, startup_complete: bool,
                             admission_closed: bool, shutdown_state: str,
                             supervisor: str = 'foreground') -> ServiceReadiness:
    if not owns_instance:
        state, reason, action = 'failed', 'INSTANCE_OWNERSHIP_LOST', 'Inspect the configured instance before starting work.'
    elif shutdown_state != 'RUNNING' or admission_closed:
        state, reason, action = 'stopping', 'RUNTIME_DRAINING', 'Observe the current shutdown; do not start a second instance.'
    elif not startup_complete:
        state, reason, action = 'starting', 'STARTUP_INCOMPLETE', 'Wait for initialization of this same generation.'
    else:
        state, reason, action = 'ready', None, None
    return ServiceReadiness(
        component='server', instance_id=identity, generation=generation,
        active_version=version, pid=pid, supervisor=supervisor, state=state,
        ready_for_queries=owns_instance and startup_complete,
        storage_initialized=startup_complete,
        admission='closed' if not owns_instance or admission_closed or shutdown_state != 'RUNNING' else 'canonical_scope_checks_required',
        reason=reason, next_action=action,
    )
