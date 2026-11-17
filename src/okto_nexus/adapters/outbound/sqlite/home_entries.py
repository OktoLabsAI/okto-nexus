"""Complete pre-pagination relations; caller supplies an authorized read UoW.

No page API is called here. Work/result builders and the authorized Attention
relation are shared with Home v1. No transcript, native control or host access.
"""
import json
import re
import sqlite3

from ....domain.attention import digest
from ....domain.home_entries import (
    ConnectionContext,
    EntryRecord,
    EntryRelations,
    SessionContext,
    activity_record,
    passive_record,
)
from ..harness.event_journal import redact
from . import home_operational_facts
from .home import FACTS, FACTS_NATIVE_PROGRESS, RESULTS, SqliteHomeQueries

# This relation is independent of the old runtime_refs preview (20). The
# persisted delivery/claim is resolved before sender filtering or pagination.
OPERATION_OWNERS = '''
WITH links AS (
 SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_domain_deliveries
 UNION SELECT server_id,executor_id,operation_id,domain_operation_id FROM execution_delivery_attempt_history
)
SELECT DISTINCT o.server_id,o.executor_id,o.operation_id,o.session_id,o.binding_id,
 o.workspace_binding_id,o.workspace_id,o.subject_agent_id,
 CASE WHEN b.handoff_id IS NOT NULL THEN 'handoff'
      WHEN l.domain_operation_id IS NOT NULL THEN 'conversation_turn'
      ELSE 'direct_operation' END AS source_type,
 CASE WHEN b.handoff_id IS NOT NULL THEN h.handoff_id
      WHEN l.domain_operation_id IS NOT NULL THEN d.operation_id
      ELSE o.operation_id END AS source_id
FROM execution_operations o
LEFT JOIN links l USING(server_id,executor_id,operation_id)
LEFT JOIN runtime_handoff_bindings b ON b.operation_id=l.domain_operation_id
LEFT JOIN handoffs h ON h.handoff_id=b.handoff_id AND h.claim_epoch=b.claim_epoch
 AND h.workspace_id=o.workspace_id
LEFT JOIN delivery_outbox d ON d.operation_id=l.domain_operation_id
 AND d.workspace_id=o.workspace_id
WHERE o.server_id=:server_id AND o.action='turn.submit'
 AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
'''

CONNECTIONS = '''
SELECT b.server_id,b.executor_id,b.binding_id,b.workspace_binding_id,
 w.workspace_id,e.agent_id,e.adapter_id AS harness_id,
 p.display_name AS workspace_label,x.label AS host_label,public.connect_id,
 CASE WHEN json_valid(a.metadata) THEN CASE WHEN json_type(a.metadata,'$.display_name')='text'
   THEN json_extract(a.metadata,'$.display_name') END END AS agent_label
FROM execution_bindings b
JOIN execution_workspace_bindings w ON w.server_id=b.server_id
 AND w.executor_id=b.executor_id AND w.workspace_binding_id=b.workspace_binding_id
JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id AND e.workspace_id=w.workspace_id
JOIN workspaces p ON p.workspace_id=w.workspace_id
JOIN execution_executors x ON x.server_id=b.server_id AND x.executor_id=b.executor_id
JOIN agents a ON a.agent_id=e.agent_id
LEFT JOIN connection_public_ids public INDEXED BY connection_public_id_binding
 ON public.server_id=b.server_id AND public.state='bound'
 AND public.canonical_ref_json IS NOT NULL
 AND public.adapter_id=e.adapter_id
 AND public.workspace_id=w.workspace_id
 AND json_extract(public.canonical_ref_json,'$.server_id')=b.server_id
 AND json_extract(public.canonical_ref_json,'$.executor_id')=b.executor_id
 AND json_extract(public.canonical_ref_json,'$.binding_id')=b.binding_id
 AND json_extract(public.canonical_ref_json,'$.endpoint_id')=b.endpoint_id
 AND json_extract(public.canonical_ref_json,'$.workspace_binding_id')=b.workspace_binding_id
 AND json_extract(public.canonical_ref_json,'$.agent_id')=e.agent_id
 AND json_extract(public.canonical_ref_json,'$.workspace_id')=w.workspace_id
WHERE b.server_id=:server_id AND (:workspace_id IS NULL OR w.workspace_id=:workspace_id)
'''

# Session context follows its own persisted tuple. Current endpoint metadata
# cannot replace a session's binding/workspace/workspace_binding or executor.
SESSIONS = '''
SELECT s.server_id,s.executor_id,s.session_id,s.binding_id,s.workspace_binding_id,
 s.workspace_id,COALESCE(o.subject_agent_id,e.agent_id) AS agent_id,s.lifecycle_state
FROM execution_sessions s
LEFT JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id
 AND o.operation_id=s.open_operation_id AND o.action='runtime.open'
 AND o.session_id=s.session_id AND o.binding_id=s.binding_id
 AND o.workspace_binding_id=s.workspace_binding_id AND o.workspace_id=s.workspace_id
LEFT JOIN execution_bindings b ON b.server_id=s.server_id AND b.executor_id=s.executor_id
 AND b.binding_id=s.binding_id AND b.workspace_binding_id=s.workspace_binding_id
LEFT JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id AND e.workspace_id=s.workspace_id
WHERE s.server_id=:server_id AND (:workspace_id IS NULL OR s.workspace_id=:workspace_id)
'''

# One metadata-only batch for conditional harness/request placement. This reads
# no operational params except the validated boolean isBlocking and method.
HARNESS_BLOCKING = '''
WITH latest AS MATERIALIZED (
 SELECT r.*,ROW_NUMBER() OVER(PARTITION BY r.server_id,r.executor_id,r.operation_id
   ORDER BY r.receipt_revision DESC) AS position
 FROM execution_receipts r JOIN execution_operations o USING(server_id,executor_id,operation_id)
 WHERE o.server_id=:server_id AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
   AND o.action='turn.submit'
)
SELECT json_object('family','operation','server_id',o.server_id,'executor_id',o.executor_id,
 'binding_id',o.binding_id,'workspace_binding_id',o.workspace_binding_id,
 'workspace_id',o.workspace_id,'agent_id',o.subject_agent_id,'session_id',o.session_id,
 'operation_id',o.operation_id,'admission_state',o.admission_state,'stage',r.stage,
 'received_at',r.received_at,'dispatch_state',d.dispatch_state) AS item
FROM execution_operations o
LEFT JOIN latest r ON r.server_id=o.server_id AND r.executor_id=o.executor_id
 AND r.operation_id=o.operation_id AND r.position=1
LEFT JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id)
WHERE o.server_id=:server_id AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
 AND o.action='turn.submit'
UNION ALL
SELECT json_object('family','request','server_id',r.server_id,'executor_id',r.executor_id,
 'session_id',r.session_id,'operation_id',r.source_operation_id,
 'binding_id',json_extract(r.operational_frame_json,'$.binding_id'),
 'workspace_binding_id',json_extract(r.operational_frame_json,'$.workspace_binding_id'),
 'workspace_id',json_extract(r.operational_frame_json,'$.workspace_id'),
 'agent_id',json_extract(r.operational_frame_json,'$.agent_id'),
 'request_id',r.canonical_request_id,'request_revision',r.request_revision,'state',r.state,
 'expires_at',r.expires_at,'stream_epoch',r.stream_epoch,'session_stream_epoch',s.stream_epoch,
 'method',json_extract(r.operational_frame_json,'$.operational_request.method'),
 'is_blocking',CASE WHEN json_extract(r.operational_frame_json,'$.operational_request.method')='item/tool/requestUserInput'
   AND json_type(r.operational_frame_json,'$.operational_request.params.isBlocking') IN ('true','false')
   THEN json_extract(r.operational_frame_json,'$.operational_request.params.isBlocking') END,
 'approval_status',ap.status,'decided_at',ap.decided_at) AS item
FROM execution_native_requests r
JOIN execution_sessions s USING(server_id,executor_id,session_id)
LEFT JOIN approvals ap ON ap.approval_id=r.canonical_request_id
WHERE r.server_id=:server_id AND json_valid(r.operational_frame_json)
 AND (:workspace_id IS NULL OR json_extract(r.operational_frame_json,'$.workspace_id')=:workspace_id)
'''

# Separate from the legacy SQL: no new facts or decision placement are sent to
# old consumers. Adapter is the exact bound endpoint, not a family guess.
HARNESS_BLOCKING_V2 = HARNESS_BLOCKING.replace(
    'WITH latest AS MATERIALIZED (',
    '''WITH native_write_receipts AS MATERIALIZED (
 SELECT r.*,ROW_NUMBER() OVER(PARTITION BY r.server_id,r.executor_id,r.operation_id
 ORDER BY r.receipt_revision DESC) AS position
 FROM execution_receipts r JOIN execution_operations o USING(server_id,executor_id,operation_id)
 WHERE o.server_id=:server_id AND (:workspace_id IS NULL OR o.workspace_id=:workspace_id)
 AND o.action IN ('input.provide','approval.decide')
), latest AS MATERIALIZED ('''
).replace(
    "'received_at',r.received_at,'dispatch_state',d.dispatch_state)",
    "'received_at',r.received_at,'dispatch_state',d.dispatch_state,"
    "'owner_generation',json_extract(o.expected_revisions_json,'$.session_owner_generation'),"
    "'stream_epoch',s.stream_epoch)").replace(
    'LEFT JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id)',
    'LEFT JOIN execution_dispatch_outbox d USING(server_id,executor_id,operation_id) '
    'LEFT JOIN execution_sessions s ON s.server_id=o.server_id AND s.executor_id=o.executor_id AND s.session_id=o.session_id'
).replace(
    "'approval_status',ap.status,'decided_at',ap.decided_at)",
    "'approval_status',ap.status,'decided_at',ap.decided_at,"
    "'owner_generation',r.session_owner_generation,'source_sequence',r.source_sequence,"
    "'adapter_id',ep.adapter_id,'decision_id',decision.decision_id,'native_operation_id',decision.native_operation_id,"
    "'decision_scope_matches',CASE WHEN reply.operation_id IS NOT NULL THEN 1 ELSE 0 END,"
    "'native_write_stage',write_receipt.stage,'native_write_possible_effect',write_receipt.possible_effect,"
    "'native_write_dispatch',write_dispatch.dispatch_state)"
).replace(
    'LEFT JOIN approvals ap ON ap.approval_id=r.canonical_request_id',
    'LEFT JOIN approvals ap ON ap.approval_id=r.canonical_request_id '
    'LEFT JOIN execution_bindings rb ON rb.server_id=r.server_id AND rb.executor_id=r.executor_id '
    "AND rb.binding_id=json_extract(r.operational_frame_json,'$.binding_id') "
    'LEFT JOIN agent_endpoints ep ON ep.endpoint_id=rb.endpoint_id '
    'LEFT JOIN execution_decisions decision ON decision.canonical_request_id=r.canonical_request_id '
    'AND decision.server_id=r.server_id AND decision.executor_id=r.executor_id '
    'LEFT JOIN execution_operations reply ON reply.server_id=r.server_id AND reply.executor_id=r.executor_id '
    'AND reply.operation_id=decision.native_operation_id AND reply.decision_id=decision.decision_id '
    "AND reply.action IN ('input.provide','approval.decide') AND reply.session_id=r.session_id "
    "AND reply.binding_id=json_extract(r.operational_frame_json,'$.binding_id') "
    "AND reply.workspace_binding_id=json_extract(r.operational_frame_json,'$.workspace_binding_id') "
    "AND reply.workspace_id=json_extract(r.operational_frame_json,'$.workspace_id') "
    "AND reply.subject_agent_id=json_extract(r.operational_frame_json,'$.agent_id') "
    "AND json_extract(reply.expected_revisions_json,'$.session_owner_generation')=r.session_owner_generation "
    'LEFT JOIN native_write_receipts write_receipt ON write_receipt.server_id=reply.server_id '
    'AND write_receipt.executor_id=reply.executor_id AND write_receipt.operation_id=reply.operation_id AND write_receipt.position=1 '
    'LEFT JOIN execution_dispatch_outbox write_dispatch ON write_dispatch.server_id=reply.server_id '
    'AND write_dispatch.executor_id=reply.executor_id AND write_dispatch.operation_id=reply.operation_id'
)


class _WorkRows(list):
    """Request-local private metadata; list items remain legacy activity JSON."""

    def __init__(self, values=(), native_progress_current=()):
        super().__init__(values)
        self.native_progress_current = list(native_progress_current)


def _progress_collection(raw):
    try:
        values = json.loads(raw) if raw is not None else []
    except (TypeError, ValueError):
        return []
    return values if isinstance(values, list) else []


def _progress_key(value):
    if not isinstance(value, dict):
        return None
    names = ('server_id', 'executor_id', 'operation_id', 'session_id', 'workspace_id',
        'agent_id', 'binding_id', 'workspace_binding_id', 'stream_epoch')
    if any(type(value.get(name)) is not str or not value[name] for name in names):
        return None
    owner = value.get('owner_generation')
    if type(owner) is not int or owner < 1:
        return None
    return (*tuple(value[name] for name in names), owner)


class SqliteHomeEntryRelations:
    """Internal, unpaged projection. Does not authenticate or grant authority.

    Service callers must first use their existing Home authorization/basis and
    pass the canonical authorized Attention relation within its live context.
    Unavailable sources remain unknown, never an exact empty inventory.
    """

    def __init__(self):
        self.home = SqliteHomeQueries()

    MAX_RELATION_ROWS = 100_000

    def _collect(self, cursor, decode, check_budget=None):
        values = []
        check_budget = check_budget or (lambda: None)
        try:
            for row in cursor:
                check_budget()
                if len(values) >= self.MAX_RELATION_ROWS:
                    # Discard the complete source on exhaustion. Never return
                    # the first N as an exact, apparently successful inventory.
                    raise sqlite3.OperationalError('Home entry source resource budget exceeded')
                values.append(decode(row))
            return values
        finally:
            cursor.close()  # UDF cleanup must not retain an unfinished statement.

    def _project(self, uow, *, relation, params, attention_relation, check_budget=None):
        include_progress = relation is FACTS and params.get('delivery_presentation_version') == 2
        if include_progress:
            relation = FACTS_NATIVE_PROGRESS
        if attention_relation is None:
            ctes = 'WITH home_attention AS MATERIALIZED (SELECT NULL AS item WHERE 0)'
            additions = {}
        else:
            ctes, additions = self.home._attention_relations(attention_relation)
        sql = ctes + ',' + relation.lstrip()[4:] + (' SELECT item,native_progress_current FROM filtered' if include_progress else ' SELECT item FROM filtered')
        progress = []
        def decode(row):
            if include_progress:
                progress.extend(_progress_collection(row[1]))
            return json.loads(row[0])
        with self.home.bounded(uow.connection):
            values = self._collect(uow.connection.execute(sql, dict(params, **additions)), decode, check_budget)
        return _WorkRows(values, progress) if include_progress else values

    def _work(self, uow, **kwargs):
        return self._project(uow, relation=FACTS, **kwargs)

    def _results(self, uow, **kwargs):
        return self._project(uow, relation=RESULTS, **kwargs)

    def _work_results(self, uow, *, params, attention_relation, check_budget):
        """Share statement-local authorized Attention, keeping both relations intact.

        Nested WITH scopes preserve the independent Work/Results CTE names.
        Results deliberately retain receiver facts outside the Work agent filter.
        Any SQLite failure discards this batch; read() retries isolated sources.
        """
        if attention_relation is None:
            ctes = 'WITH home_attention AS MATERIALIZED (SELECT NULL AS item WHERE 0)'
            additions = {}
        else:
            ctes, additions = self.home._attention_relations(attention_relation)
        include_progress = params.get('delivery_presentation_version') == 2
        work_relation = FACTS_NATIVE_PROGRESS if include_progress else FACTS
        progress_column = 'native_progress_current' if include_progress else 'NULL'
        results = re.sub(r':agent_id\b', ':result_agent_id', RESULTS)
        sql = (ctes + " SELECT 'work' AS section,item," + progress_column + ' FROM (' + work_relation
            + " SELECT item,native_progress_current FROM filtered LIMIT :batch_source_limit) UNION ALL SELECT 'results',item,NULL FROM ("
            + results + ' SELECT item FROM filtered LIMIT :batch_source_limit)')
        values = {'work': _WorkRows() if include_progress else [], 'results': []}
        with self.home.bounded(uow.connection):
            cursor = uow.connection.execute(sql, dict(params, result_agent_id=None,
                batch_source_limit=self.MAX_RELATION_ROWS + 1, **additions))
            try:
                for row in cursor:
                    check_budget()
                    section = values[row[0]]
                    # The existing ceiling belongs to each complete source,
                    # not to the sum of two otherwise valid source relations.
                    if len(section) >= self.MAX_RELATION_ROWS:
                        raise sqlite3.OperationalError('Home entry source resource budget exceeded')
                    section.append(json.loads(row[1]))
                    if include_progress and row[0] == 'work':
                        section.native_progress_current.extend(_progress_collection(row[2]))
            finally:
                cursor.close()
        return values['work'], values['results']

    def _can_batch_work_results(self):
        # Custom query ports/fault injection retain their isolated semantics.
        return all(getattr(getattr(self, name), '__func__', None) is getattr(SqliteHomeEntryRelations, name)
            for name in ('_work', '_results', '_project'))

    def _rows(self, uow, sql, params, check_budget=None):
        with self.home.bounded(uow.connection):
            return self._collect(uow.connection.execute(sql, params), dict, check_budget)

    def _attention(self, uow, relation, check_budget=None):
        sql, params = relation
        with self.home.bounded(uow.connection):
            return self._collect(uow.connection.execute(sql + ' SELECT item FROM filtered', params), lambda row: json.loads(row[0]), check_budget)

    def blocking(self, uow, *, scope, server_id, relations, check_budget):
        if relations.presentation_version == 2:
            # read() already assembled the same v2 batch in this UoW.
            return
        with self.home.bounded(uow.connection):
            relations.harness_blocking = self._collect(uow.connection.execute(HARNESS_BLOCKING,
                dict(server_id=server_id, workspace_id=scope.get('workspace_id'))),
                lambda row: json.loads(row[0]), check_budget)

    def read(self, uow, *, scope, server_id, now, attention_relation, check_budget=None, presentation_version=1):
        """Return all canonical relations before UI-020 sorting/count/paging.

        ``scope`` is the already normalized/authorized Home workspace/agent
        scope. State/quick filters belong after enrichment, not at source read.
        No authority is inferred from the caller's possession of these IDs.
        """
        if presentation_version == 2:
            # Workspace authorization has already run. Agent is a visual
            # selection, never permission to hide a productive sibling before
            # calculating a connection's operational state.
            scope = dict(scope, agent_id=None)
        params = {'server_id': server_id, 'workspace_id': scope.get('workspace_id'),
                      'agent_id': scope.get('agent_id'), 'home_now': now, 'state': 'all',
                      'delivery_presentation_version': presentation_version}
        status = {}
        check_budget = check_budget or (lambda: None)

        def source(name, call):
            check_budget()
            try:
                value = call()
                status[name] = 'ready'
                return value
            except sqlite3.Error:
                status[name] = 'unavailable'
                return []

        # A missing canonical occurrence relation is unknown, not an empty
        # successful Attention source. Policy/permission errors are never caught.
        occurrences = source('attention', lambda: self._attention(uow, attention_relation, check_budget)) if attention_relation is not None else []
        if attention_relation is None:
            status['attention'] = 'unavailable'
        effective_attention = attention_relation if status['attention'] == 'ready' else None
        combined = None
        if self._can_batch_work_results():
            check_budget()
            try:
                combined = self._work_results(uow, params=params,
                    attention_relation=effective_attention, check_budget=check_budget)
            except sqlite3.Error:
                # Preserve source isolation: e.g. a missing Results table must
                # not erase independently readable Work (or the reverse).
                pass
        if combined is None:
            work = source('work', lambda: self._work(uow, params=params, attention_relation=effective_attention, check_budget=check_budget))
            results = source('results', lambda: self._results(uow, params=dict(params, agent_id=None), attention_relation=effective_attention, check_budget=check_budget))
        else:
            work, results = combined
            status.update(work='ready', results='ready')
        raw_connections = source('connections', lambda: self._rows(uow, CONNECTIONS, params, check_budget))
        raw_sessions = source('sessions', lambda: self._rows(uow, SESSIONS, params, check_budget))
        owners = source('correlations', lambda: self._rows(uow, OPERATION_OWNERS, params, check_budget))
        connections = {}
        for row in raw_connections:
            check_budget()
            for key in ('workspace_label', 'host_label', 'agent_label'):
                value = row[key]
                maximum = 120 if key == 'agent_label' else 160
                row[key] = (' '.join(redact(value).split())[:maximum] or None) if type(value) is str and (key != 'agent_label' or len(value.strip()) <= maximum) else None
            connections[self._connection_key(row)] = ConnectionContext(**row)
        sessions = {(row['server_id'], row['executor_id'], row['session_id']): SessionContext(**row) for row in raw_sessions}
        entries = [activity_record(item) for item in work]
        by_attention = {}
        for entry in entries:
            check_budget()
            for reference in entry.activity['attention_refs']:
                check_budget()
                by_attention[reference] = entry
        by_source = {(e.source_ref['type'], e.source_ref['id'], e.target['executor_id'], e.target['session_id'])
                     if e.source_ref['type'] == 'direct_operation' else
                     (e.source_ref['type'], e.source_ref['id']): e for e in entries}
        by_operation, represented_sessions = {}, set()
        per_entry_sessions = {e.id: {} for e in entries}
        per_entry_connections = {e.id: set() for e in entries}
        covered_connections = set()
        for row in owners:
            check_budget()
            source_key = (row['source_type'], row['source_id'], row['executor_id'], row['session_id']) if row['source_type'] == 'direct_operation' else (row['source_type'], row['source_id'])
            parent = by_source.get(source_key)
            if parent is None or parent.workspace_id != row['workspace_id']:
                continue
            key = (row['server_id'], row['executor_id'], row['operation_id'])
            by_operation[key] = parent
            parent.operations.append(dict(executor_id=row['executor_id'], session_id=row['session_id'], operation_id=row['operation_id']))
            connection_key = self._connection_key(dict(row, agent_id=row['subject_agent_id']))
            if connection_key in connections:
                per_entry_connections[parent.id].add(connection_key)
                covered_connections.add(connection_key)
            session_key = (row['server_id'], row['executor_id'], row['session_id'])
            session = sessions.get(session_key)
            # An operation's own binding tuple must agree with the historical
            # session; a newer binding of the same agent is not a substitute.
            if session and (session.binding_id, session.workspace_binding_id, session.workspace_id, session.agent_id) == (
                    row['binding_id'], row['workspace_binding_id'], row['workspace_id'], row['subject_agent_id']):
                per_entry_sessions[parent.id][session_key] = session
                represented_sessions.add(session_key)
        for entry in entries:
            check_budget()
            entry.sessions = tuple(per_entry_sessions[entry.id][key] for key in sorted(per_entry_sessions[entry.id]))
            contexts = per_entry_connections[entry.id]
            entry.registered_connections = tuple(connections[key] for key in sorted(contexts))
            if len(contexts) == 1:
                entry.connection = connections.get(next(iter(contexts)))
                if entry.connection:
                    entry.agent_id = entry.connection.agent_id

        # Results enrich exactly one retained logical parent. A retained old
        # claim must not attach to a newer claim merely by handoff_id.
        by_result = {}
        for result in results:
            check_budget()
            target = result['detail_target']
            parent = None
            if target['kind'] == 'result':
                parent = by_operation.get((target['server_id'], target['executor_id'], target['operation_id']))
            elif result['verification_state'] != 'historical_claim':
                parent = by_source.get(('handoff', target.get('handoff_id')))
            if parent and parent.workspace_id == result['workspace_id']:
                parent.results.append(result)
            else:
                if scope.get('agent_id') and result['agent_id'] != scope['agent_id']:
                    continue
                parent = self._orphan_result(result)
                if target['kind'] == 'result':
                    key = (target['server_id'], target['executor_id'], target['session_id'])
                    session = sessions.get(key)
                    if session and session.workspace_id == result['workspace_id']:
                        parent.sessions = (session,)
                        parent.connection = connections.get(self._connection_key(session.__dict__))
                        represented_sessions.add(key)
                entries.append(parent)
            by_result[result['id']] = parent

        server_attention = []
        for occurrence in occurrences:
            check_budget()
            workspace = occurrence['workspace_id']
            if workspace is None:
                server_attention.append(occurrence)
                continue
            if scope.get('workspace_id') is not None and workspace != scope['workspace_id']:
                continue
            parent = by_operation.get((server_id, occurrence.get('executor_id'), occurrence.get('operation_id')))
            if parent is None and occurrence.get('result_id'):
                parent = by_result.get(occurrence['result_id'])
            if parent is None:
                parent = by_attention.get(occurrence['attention_id'])
            # Occurrence scope remains the receiver's canonical fact; selecting
            # the work sender does not rewrite recipient/category/actions.
            if parent and parent.workspace_id == workspace:
                parent.attention.append(occurrence)
            elif not scope.get('agent_id') or occurrence['agent_id'] == scope['agent_id']:
                parent = self._orphan_attention(occurrence)
                key = (server_id, occurrence.get('executor_id'), occurrence.get('session_id'))
                session = sessions.get(key)
                if session and session.workspace_id == workspace:
                    parent.sessions = (session,)
                    parent.connection = connections.get(self._connection_key(session.__dict__))
                    represented_sessions.add(key)
                entries.append(parent)

        represented_connections = set(covered_connections)
        for entry in entries:
            for session in entry.sessions:
                represented_connections.add(self._connection_key(session.__dict__))
        for key, session in sessions.items():
            check_budget()
            if key in represented_sessions or scope.get('agent_id') and session.agent_id != scope['agent_id']:
                continue
            entry = passive_record(session)
            entry.sessions = (session,)
            entry.connection = connections.get(self._connection_key(session.__dict__))
            represented_connections.add(self._connection_key(session.__dict__))
            entries.append(entry)
        for key, connection in connections.items():
            check_budget()
            if key in represented_connections or scope.get('agent_id') and connection.agent_id != scope['agent_id']:
                continue
            entry = passive_record(connection)
            entry.connection = connection
            entries.append(entry)
        relations = EntryRelations(entries, server_attention, status,
            connection_count=len(connections) if status['connections'] == 'ready' else None,
            connections=tuple(connections[key] for key in sorted(connections)) if status['connections'] == 'ready' else None)
        if presentation_version == 2:
            relations.presentation_version = 2
            operational_rows = source('operational_sessions', lambda: self._rows(uow, home_operational_facts.SESSIONS, params, check_budget))
            leases = source('operational_leases', lambda: self._rows(uow, home_operational_facts.LEASES, params, check_budget))
            if status['operational_sessions'] == status['operational_leases'] == 'ready':
                relations.operational_sessions = home_operational_facts.normalize(operational_rows, leases, check_budget)
            rows = source('operational_dependencies', lambda: self._rows(uow, HARNESS_BLOCKING_V2, params, check_budget))
            if status['operational_dependencies'] == 'ready':
                relations.harness_blocking = [json.loads(row['item']) for row in rows]
                if status['work'] == 'ready':
                    positive_progress = set()
                    for proof in getattr(work, 'native_progress_current', ()):
                        check_budget()
                        key = _progress_key(proof)
                        if key is not None:
                            positive_progress.add(key)
                    for operation in relations.harness_blocking:
                        check_budget()
                        if operation.get('family') == 'operation' and _progress_key(operation) in positive_progress:
                            operation['productive_progress_current'] = True
            relations.operational_source_status = {name: status.pop(name) for name in
                ('operational_sessions', 'operational_leases', 'operational_dependencies')}
        return relations

    def external(self, uow, *, scope, server_id, now, config, observations, relations, check_budget):
        """Read the canonical complete observation source in this same UoW.

        all_current has its own65536/5s ceiling and refuses an incomplete
        aggregate. Authentication was already performed by the Home caller.
        Native association requires the validated persisted correlation view.
        """
        check_budget()
        if not config.feature_observations:
            relations.source_status['external'] = 'disabled'
            return
        rows = observations.repo.all_current(uow, agent_id=scope.get('agent_id'), workspace_id=scope.get('workspace_id'))
        values = []
        for start in range(0, len(rows), 256):
            check_budget()
            values.extend(observations._project_current(uow, rows[start:start+256], now, config))
        session_owners, operation_owners, external_attention = {}, {}, {}
        for entry in relations.entries:
            check_budget()
            if entry.kind == 'attention':
                for occurrence in entry.attention:
                    check_budget()
                    observation = occurrence.get('external_observation')
                    if occurrence['source_type'] == 'external_observation' and isinstance(observation, dict):
                        key = (observation['source_id'], observation['observed_instance_id'], observation['generation'])
                        external_attention.setdefault(key, []).append((entry.id, occurrence))
            for session in entry.sessions:
                check_budget()
                key = (session.server_id, session.executor_id, session.session_id, session.workspace_id)
                session_owners.setdefault(key, {})[entry.id] = entry
            for operation in entry.operations:
                check_budget()
                operation_owners[(operation['executor_id'], operation['operation_id'])] = entry
        absorbed = set()
        for item in values:
            check_budget()
            ref = item.get('canonical_session_ref')
            matched = {} if not ref else session_owners.get((ref['server_id'], ref['executor_id'], ref['session_id'], item['workspace_id']), {})
            receipt = (item.get('canonical_observation') or {}).get('last_received_receipt') or {}
            parent = operation_owners.get((ref['executor_id'], receipt.get('operation_id'))) if ref and receipt.get('status') == 'verified' else None
            parent = parent if parent and parent.id in matched else None
            related = external_attention.get((item['source_id'], item['observed_instance_id'], item['generation']), [])
            if parent:
                parent.external.append(item)
                parent.attention.extend(occurrence for _, occurrence in related)
                absorbed.update(entry_id for entry_id, _ in related)
                continue
            state = 'stale' if item['freshness'] == 'stale' else 'offline' if item['freshness'] == 'unavailable' else 'running' if item['activity_state'] == 'working' else 'idle' if item['activity_state'] == 'idle' else 'configured'
            entry = EntryRecord(id='home_external_' + digest([1, server_id, item['source_id'], item['observed_instance_id'], item['generation']]),
                kind='external', source_ref=dict(type='external_observation', id=item['observed_instance_id'], revision=digest(item)),
                workspace_id=item['workspace_id'], agent_id=item['agent_id'], title='External activity',
                display_state=state, evidence='reported' if item['freshness'] == 'current' else 'unknown',
                target=dict(kind='external_observation', server_id=server_id, workspace_id=item['workspace_id'],
                    source_id=item['source_id'], observed_instance_id=item['observed_instance_id'], generation=item['generation']), external=[item])
            if len(matched) == 1:
                entry.connection = next(iter(matched.values())).connection
            entry.attention.extend(occurrence for _, occurrence in related)
            absorbed.update(entry_id for entry_id, _ in related)
            relations.entries.append(entry)
        relations.entries[:] = [entry for entry in relations.entries if entry.id not in absorbed]
        relations.source_status['external'] = 'ready'

    @staticmethod
    def _connection_key(row):
        return tuple(row[k] for k in ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id'))

    @staticmethod
    def _orphan_result(result):
        state = ('result_available_cleanup_pending' if result['cleanup_state'] else 'turn_completed') if result['outcome'] == 'SUCCEEDED' else 'failed' if result['outcome'] in ('FAILED', 'REJECTED') else 'cancelled' if result['outcome'] == 'CANCELLED' else 'completed'
        return EntryRecord(id=result['id'], kind='work', source_ref=result['source_ref'],
            workspace_id=result['workspace_id'], agent_id=result['agent_id'], title=result['title'],
            display_state=state,
            evidence='confirmed', target=result['detail_target'], results=[result])

    @staticmethod
    def _orphan_attention(occurrence):
        return EntryRecord(id='home_entry_' + digest([1, 'attention', occurrence['attention_id']]),
            kind='attention', source_ref=dict(type=occurrence['source_type'], id=occurrence['source_id'],
                revision=occurrence['source_revision']), workspace_id=occurrence['workspace_id'],
            agent_id=occurrence['agent_id'], title='Needs attention',
            display_state='awaiting_operator' if occurrence['category'] == 'action_required' else
                'awaiting_agent' if occurrence['kind'] == 'question_waiting_for_agent' else 'outcome_unknown',
            evidence='unknown' if occurrence['freshness'] != 'current' else 'confirmed',
            target=None, attention=[occurrence])
