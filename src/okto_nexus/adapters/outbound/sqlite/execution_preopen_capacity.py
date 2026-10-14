"""Read exact retained capacity for an embedded opening under a fenced owner."""
import json

from .capacity_admissions import SqliteCapacityAdmissionRepository, conflict


class SqlitePreopenCapacityRepository:
    def fenced_admission(self, uow, channel, *, session_id, opening_operation_id):
        row = uow.connection.execute(
            'SELECT a.domain_operation_id,o.intent_hash,o.expected_revisions_json '
            'FROM execution_capacity_admissions a JOIN execution_sessions s '
            'USING(server_id,executor_id,session_id) JOIN execution_operations o '
            'ON o.server_id=s.server_id AND o.executor_id=s.executor_id AND o.operation_id=s.open_operation_id '
            'JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id) '
            'JOIN execution_executors e ON e.server_id=s.server_id AND e.executor_id=s.executor_id '
            'WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? AND s.open_operation_id=? '
            "AND s.lifecycle_state IN ('OPEN_PENDING','FAILED') AND o.action='runtime.open' "
            "AND e.kind='embedded' AND e.owner_instance_id=? AND e.generation=? "
            "AND e.revoked_at IS NULL AND e.control_state='CONTROL_READY' AND d.connection_generation<? "
            'AND NOT EXISTS(SELECT 1 FROM execution_local_publications p '
            'WHERE p.server_id=s.server_id AND p.executor_id=s.executor_id AND p.session_id=s.session_id) '
            'AND NOT EXISTS(SELECT 1 FROM execution_local_streams l '
            'WHERE l.server_id=s.server_id AND l.executor_id=s.executor_id AND l.session_id=s.session_id) '
            'AND NOT EXISTS(SELECT 1 FROM execution_receipts r JOIN execution_operations ro '
            'USING(server_id,executor_id,operation_id) WHERE ro.server_id=s.server_id '
            'AND ro.executor_id=s.executor_id AND ro.session_id=s.session_id)',
            (channel.server_id, channel.executor_id, session_id, opening_operation_id,
             channel.connection_id, channel.connection_generation, channel.connection_generation)).fetchone()
        if row is None:
            return None
        admission = SqliteCapacityAdmissionRepository().get(uow, row['domain_operation_id'])
        request, consumption = admission.reservation.request, admission.consumption
        if (request.unit != 'new_session' or request.scope.session_id != session_id
                or request.scope.server_id != channel.server_id or request.scope.executor_id != channel.executor_id
                or request.scope.connection_generation >= channel.connection_generation
                or consumption.opening_operation_id != opening_operation_id
                or consumption.opening_intent_hash != row['intent_hash']
                or any(getattr(request.scope, key) != value
                    for key, value in json.loads(row['expected_revisions_json']).items())):
            raise conflict('PREOPEN_CAPACITY_IDENTITY_MISMATCH')
        return admission
