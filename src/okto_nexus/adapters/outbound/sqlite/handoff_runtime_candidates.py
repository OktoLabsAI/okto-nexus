"""Paged logical candidates and exact capacity snapshots; no host I/O."""
import hashlib
import json

from nexus_connector_core import CAPACITY_CONTRACT_REVISION, CapacityRequest, CapacityScope

from ....application.execution_domain_delivery import delivery_session_context, select_delivery_session
from ....application.one_shot_runtime import digest, host_limit
from ....domain.base import new_id
from ....errors import ErrorCode, OktoNexusError
from .execution_agent_revisions import current_agent_revisions
from .handoff_origins import SqliteHandoffOriginRepo


def unavailable(reason):
    return OktoNexusError(ErrorCode.CONFLICT, reason, {'reason': reason})


class SqliteHandoffCandidateRepository:
    def __init__(self, *, attempts, availability, pool_factory):
        self.attempts, self.availability, self.pool_factory = attempts, availability, pool_factory

    def proved_no_effect(self, uow, lease):
        row = uow.connection.execute('SELECT * FROM handoff_runtime_proved_no_effect '
            'WHERE handoff_id=? AND workspace_id=? AND claim_epoch=?',
            (lease.handoff_id, lease.workspace_id, lease.claim_generation)).fetchone()
        if row is None:
            return None
        operation = uow.connection.execute('SELECT * FROM delivery_outbox WHERE operation_id=?',
            (row['operation_id'],)).fetchone()
        return dict(row) | {'operation': dict(operation)}

    def retire_no_effect(self, uow, proof, *, now_iso, now_epoch):
        conn = uow.connection
        updated = conn.execute("UPDATE handoff_runtime_attempts SET state='FAILED_NO_EFFECT',"
            "active=0,disposition='RELEASE',reason=?,updated_at=? "
            "WHERE attempt_id=? AND operation_id=? AND state='CLAIM_COMMITTED' AND active=1",
            (proof['error_code'] or 'OPENING_NO_EFFECT', now_iso,
             proof['attempt_id'], proof['operation_id']))
        if updated.rowcount != 1:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The recovered attempt changed.', {})
        previous = conn.execute('SELECT failure_count FROM handoff_runtime_no_effect_retries '
            'WHERE handoff_id=? AND agent_id=?', (proof['handoff_id'], proof['agent_id'])).fetchone()
        count = min((previous[0] if previous else 0) + 1, 32)
        delay = min(300, 15 * 2 ** min(count - 1, 5))
        conn.execute('INSERT INTO handoff_runtime_no_effect_retries '
            '(handoff_id,agent_id,failure_count,retry_after,last_operation_id,updated_at) '
            'VALUES(?,?,?,?,?,?) ON CONFLICT(handoff_id,agent_id) DO UPDATE SET '
            'failure_count=excluded.failure_count,retry_after=excluded.retry_after,'
            'last_operation_id=excluded.last_operation_id,updated_at=excluded.updated_at',
            (proof['handoff_id'], proof['agent_id'], count, now_epoch + delay,
             proof['operation_id'], now_iso))

    def agents_page(self, uow, lease, *, allow_new, limit, now_epoch):
        # UNION collapses grants, endpoints and physical slots to one agent.
        # Recovery includes revoked/disabled candidates absent from the catalog.
        query = ("WITH candidates AS (SELECT a.agent_id FROM handoff_runtime_attempts a "
            "LEFT JOIN execution_capacity_admissions c ON c.domain_operation_id=a.operation_id "
            "WHERE a.workspace_id=? AND a.handoff_id=? AND a.claim_generation=? AND a.active=1 "
            "AND (a.operation_id IS NULL OR c.state IS NULL OR c.state<>'CONSUMED')")
        args = (lease.workspace_id, lease.handoff_id, lease.claim_generation)
        if allow_new:
            query += (" UNION SELECT e.agent_id FROM agent_endpoints e WHERE e.workspace_id=? "
                      "AND e.protocol='nxl-r4' AND e.enabled=1 AND e.activation_state='approved' "
                      "AND NOT EXISTS (SELECT 1 FROM handoff_runtime_no_effect_retries f "
                      "WHERE f.handoff_id=? AND f.agent_id=e.agent_id AND f.retry_after>?)")
            args += (lease.workspace_id, lease.handoff_id, now_epoch)
        query += ') '
        cursor = json.loads(lease.candidate_cursor) if lease.candidate_cursor else None
        if cursor is not None and (type(cursor) is not dict or set(cursor) != {'anchor', 'after'}
                or any(type(v) is not str or len(v) > 256 for v in cursor.values())):
            raise ValueError('Invalid candidate cursor.')
        if cursor is None:
            count = uow.connection.execute(query + 'SELECT count(*) FROM candidates', args).fetchone()[0]
            if not count:
                return (), '', False
            seed = f'{lease.handoff_id}:{lease.claim_generation}'.encode()
            offset = int.from_bytes(hashlib.sha256(seed).digest()[:8], 'big') % count
            anchor = uow.connection.execute(query + 'SELECT agent_id FROM candidates ORDER BY agent_id LIMIT 1 OFFSET ?',
                                           (*args, offset)).fetchone()[0]
            after = ''
        else:
            anchor, after = cursor['anchor'], cursor['after']
        # Stable circular keyset order, materializing at most limit+1 identities.
        where, tail = '', ()
        if after:
            where = ' WHERE ((agent_id < ?),agent_id) > (?,?)'
            tail = (anchor, int(after < anchor), after)
        rows = uow.connection.execute(query + 'SELECT agent_id FROM candidates' + where
            + ' ORDER BY (agent_id < ?),agent_id LIMIT ?', (*args, *tail, anchor, limit + 1)).fetchall()
        more = len(rows) > limit
        agents = tuple(row[0] for row in rows[:limit])
        if more:
            next_cursor = {'anchor': anchor, 'after': agents[-1]}
        else:
            # Advance the first candidate on the next round, even for the same
            # handoff/generation. A deleted anchor is still a valid lexical key.
            row = uow.connection.execute(query + 'SELECT agent_id FROM candidates '
                'ORDER BY (agent_id <= ?),agent_id LIMIT 1', (*args, anchor)).fetchone()
            next_cursor = {'anchor': row[0] if row else anchor, 'after': ''}
            if not agents and row is not None:
                # Earlier pages may still own unresolved cleanup. An empty
                # suffix is not evidence that the entire handoff is settled.
                more = True
        return agents, json.dumps(next_cursor, ensure_ascii=True, separators=(',', ':')), more

    def active(self, uow, lease, agent_id):
        row = uow.connection.execute('SELECT attempt_id FROM handoff_runtime_attempts '
            'WHERE workspace_id=? AND handoff_id=? AND claim_generation=? AND agent_id=? AND active=1',
            (lease.workspace_id, lease.handoff_id, lease.claim_generation, agent_id)).fetchone()
        return self.attempts.get(uow, row[0]) if row else None

    def target(self, uow, handoff, endpoint_id):
        origin = SqliteHandoffOriginRepo().get(uow, workspace_id=handoff.workspace_id, handoff_id=handoff.handoff_id)
        binding, affinity = delivery_session_context(uow, endpoint_id,
            sender_agent_id=handoff.from_agent_id, source_session_key=origin.source_session_key)
        _, session_id = select_delivery_session(uow, endpoint_id,
            sender_agent_id=handoff.from_agent_id, source_session_key=origin.source_session_key)
        return binding, affinity, session_id

    def request(self, uow, *, handoff, agent_id, target, attempt_id):
        binding, affinity, session_id = target
        host = self.availability.current_host(binding['server_id'], binding['executor_id'])
        if host is None:
            raise unavailable('CAPACITY_PROTOCOL_UNSUPPORTED')
        executor = uow.connection.execute('SELECT kind FROM execution_executors WHERE server_id=? AND executor_id=?',
            (binding['server_id'], binding['executor_id'])).fetchone()
        if executor is None or (executor['kind'] == 'remote' and not host.channel.supports_work_containment):
            # A reservation alone is insufficient: automatic work also needs a
            # session-scoped revocation and durable physical-release path.
            raise unavailable('CAPACITY_PROTOCOL_UNSUPPORTED')
        observation = host.observations.get(binding['binding_id'])
        if not host.boot_id or observation is None or observation[2] <= self.availability.monotonic():
            raise unavailable('STALE_OBSERVATION')
        conn = uow.connection
        if affinity.policy == 'one_shot':
            occupied = tuple(row[0] for row in conn.execute(
                "SELECT json_extract(request_json,'$.scope.session_id') FROM handoff_runtime_attempts "
                "WHERE agent_id=? AND active=1 AND operation_id IS NULL", (agent_id,)))
            warm = self.pool_factory(conn).preview_immediate(pool_id=agent_id, host_id=binding['executor_id'],
                configuration=digest(conn, binding), host_limit=host_limit(conn, binding['executor_id']),
                exclude_resource_ids=occupied)
            session_id = warm.resource_id if warm else None
        unit, owner_generation = ('next_turn' if session_id else 'new_session'), 1
        if session_id:
            row = conn.execute('SELECT owner_generation,lifecycle_state,lease_state FROM execution_sessions '
                'WHERE server_id=? AND executor_id=? AND session_id=?',
                (binding['server_id'], binding['executor_id'], session_id)).fetchone()
            if row is None or row['lifecycle_state'] != 'READY' or row['lease_state'] != 'ACTIVE':
                raise unavailable('RECOVERING')
            owner_generation = row['owner_generation']
        else:
            session_id = new_id('exs')
        server_id, revisions, _ = current_agent_revisions(None, agent_id=agent_id, uow=uow)
        if server_id != binding['server_id']:
            raise unavailable('STALE_OBSERVATION')
        scope = CapacityScope(server_id=server_id, executor_id=binding['executor_id'],
            agent_id=agent_id, binding_id=binding['binding_id'], workspace_id=handoff.workspace_id,
            workspace_binding_id=binding['workspace_binding_id'], session_id=session_id,
            connection_generation=host.channel.connection_generation, session_owner_generation=owner_generation,
            authorization_revision=revisions.authorization, configuration_revision=revisions.configuration,
            credential_epoch=revisions.credential_epoch, binding_revision=binding['binding_revision'], boot_id=host.boot_id)
        return CapacityRequest(CAPACITY_CONTRACT_REVISION, attempt_id, scope, unit,
                               affinity.capacity_key(session_id), 10000)
