"""Read-only invalidation of cached diagnostics against current configuration."""
import json

from .execution_agent_revisions import current_agent_revisions
from ....errors import OktoNexusError


class SqliteCapacityObservationScopes:
    def __init__(self, factory):
        self.factory = factory

    def current(self, uow, requests):
        if not requests:
            return set()
        agents = {r.scope.agent_id for r in requests}
        if len(requests) > 100 or len(agents) != 1:
            raise ValueError('Invalid diagnostic scope page.')
        try:
            server_id, revisions, _ = current_agent_revisions(self.factory,
                agent_id=next(iter(agents)), uow=uow, persist=False)
        except OktoNexusError:
            return set()
        candidates = [r for r in requests if r.scope.server_id == server_id and (
            r.scope.authorization_revision, r.scope.configuration_revision, r.scope.credential_epoch
        ) == (revisions.authorization, revisions.configuration, revisions.credential_epoch)]
        if not candidates:
            return set()
        # A single bounded join, not one query per context. No payload, secret,
        # authority token or reservation identity is returned to the read model.
        rows = uow.connection.execute('''
            WITH requested AS (
                SELECT json_extract(value,'$.hash') AS hash,
                       json_extract(value,'$.scope') AS scope,
                       json_extract(value,'$.unit') AS unit FROM json_each(?)
            )
            SELECT q.hash FROM requested q
            JOIN execution_bindings b ON b.server_id=json_extract(q.scope,'$.server_id')
                AND b.executor_id=json_extract(q.scope,'$.executor_id')
                AND b.binding_id=json_extract(q.scope,'$.binding_id')
            JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id
            JOIN runtime_profiles p ON p.profile_id=ep.profile_id
            JOIN execution_executors e USING(server_id,executor_id)
            JOIN execution_workspace_bindings w USING(server_id,executor_id,workspace_binding_id)
            JOIN execution_realizations r ON r.server_id=b.server_id AND r.executor_id=b.executor_id
                AND r.realization_ref=b.realization_ref
            LEFT JOIN execution_sessions s ON s.server_id=b.server_id AND s.executor_id=b.executor_id
                AND s.session_id=json_extract(q.scope,'$.session_id')
            LEFT JOIN execution_agent_recovery recovery ON recovery.server_id=b.server_id
                AND recovery.executor_id=b.executor_id AND recovery.agent_id=ep.agent_id
            WHERE ep.agent_id=json_extract(q.scope,'$.agent_id') AND r.subject_agent_id=ep.agent_id
              AND ep.protocol='nxl-r4' AND ep.enabled=1 AND ep.activation_state='approved'
              AND ep.health<>'quarantined' AND p.enabled=1
              AND e.control_state='CONTROL_READY' AND e.revoked_at IS NULL
              AND e.generation=json_extract(q.scope,'$.connection_generation')
              AND b.binding_revision=json_extract(q.scope,'$.binding_revision')
              AND b.workspace_binding_id=json_extract(q.scope,'$.workspace_binding_id')
              AND w.workspace_id=json_extract(q.scope,'$.workspace_id') AND w.status='READY'
              AND r.workspace_binding_id=b.workspace_binding_id
              AND r.revision=b.realization_revision AND r.status='READY'
              AND (recovery.state IS NULL OR (recovery.state='READY' AND recovery.generation=e.generation))
              AND ((q.unit='new_session' AND s.session_id IS NULL
                    AND json_extract(q.scope,'$.session_owner_generation')=1)
                OR (s.binding_id=b.binding_id AND s.workspace_id=w.workspace_id
                    AND s.workspace_binding_id=w.workspace_binding_id
                    AND s.owner_generation=json_extract(q.scope,'$.session_owner_generation')
                    AND ((q.unit='next_turn' AND s.lifecycle_state='READY' AND s.lease_state='ACTIVE')
                      OR (q.unit='new_session' AND s.lifecycle_state IN ('OPEN_PENDING','READY')))))
        ''', (json.dumps([dict(hash=r.request_hash, scope=r.scope.to_dict(), unit=r.unit)
                          for r in candidates]),))
        return {row[0] for row in rows}
