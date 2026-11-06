"""One filtered SQL relation for attention pages, totals and viewing state."""
from contextlib import contextmanager
import hashlib
import importlib
import json
import sqlite3
import time

from ....domain.attention import canonical, with_preferences
from ....errors import ErrorCode, OktoNexusError


class _SetDigest:
    """Order-independent fingerprint; a page fence, never authorization."""
    def __init__(self):
        self.total, self.count = 0, 0

    def step(self, value):
        self.total = (self.total + int.from_bytes(hashlib.sha256(value.encode()).digest(), 'big')) % (1 << 256)
        self.count += 1

    def finalize(self):
        return hashlib.sha256(f'{self.count}:{self.total:064x}'.encode()).hexdigest()


class SqliteAttentionQueries:
    QUERY_SECONDS = 5.0

    @contextmanager
    def _relation(self, uow, *, filters, now, config, access, context):
        conn = uow.connection
        sources, policies, projectors, functions = [], {}, {}, []
        deadline = time.monotonic() + self.QUERY_SECONDS
        expired = False

        def interrupt():
            nonlocal expired
            expired = time.monotonic() >= deadline
            return int(expired)

        def project(family, facts, observed_at):
            if interrupt():
                raise TimeoutError
            return canonical(projectors[family](json.loads(facts), observed_at, policies[family]))

        def preferences(item, seen, snooze, revision, observed_at):
            return canonical(with_preferences(json.loads(item), seen_at=seen, snoozed_until=snooze,
                                               revision=revision or 0, now=observed_at))

        registered = False
        try:
            conn.set_progress_handler(interrupt, 1000)
            for family in ('native', 'operations'):
                adapter = importlib.import_module('.attention_' + family, __package__)
                application = importlib.import_module('okto_nexus.application.attention_' + family)
                sources.append("SELECT '" + family + "' AS family, facts FROM (" + adapter.SOURCE_SQL + ')')
                policies[family] = adapter.build_policy(uow, config=config, access=access, context=context, now=now)
                projectors[family] = application.project
                functions.extend(getattr(adapter, 'SQL_FUNCTIONS', ()))
            registered = True
            conn.create_function('nexus_attention_project_v1', 3, project, deterministic=True)
            conn.create_function('nexus_attention_preferences_v1', 5, preferences, deterministic=True)
            conn.create_aggregate('nexus_attention_set_digest_v1', 1, _SetDigest)
            for name, arity, function in functions:
                conn.create_function(name, arity, function, deterministic=True)
            params = dict(now=now, workspace_id=filters.get('workspace_id'), agent_id=filters.get('agent_id'))
            clauses = []
            for name in ('workspace_id', 'agent_id', 'category', 'kind', 'priority'):
                if name in filters:
                    params['filter_' + name] = filters[name]
                    clauses.append("json_extract(item,'$." + name + "')=:filter_" + name)
            state = filters['state']
            if state == 'active':
                clauses.append("json_extract(item,'$.active')=1")
            elif state != 'all':
                params['filter_state'] = state
                clauses.append("json_extract(item,'$.resolution')=:filter_state")
            seen = filters['seen']
            if seen in ('seen', 'unseen'):
                clauses.append("json_extract(item,'$.seen_state.seen')=" + ('1' if seen == 'seen' else '0'))
            elif seen == 'snoozed':
                clauses.append("json_extract(item,'$.seen_state.snoozed')=1")
            relation = '''WITH source_facts AS (''' + ' UNION ALL '.join(sources) + '''),
                projected AS MATERIALIZED (
                    SELECT nexus_attention_project_v1(family,facts,:now) AS items FROM source_facts),
                occurrences AS MATERIALIZED (
                    SELECT value AS item FROM projected, json_each(projected.items)),
                viewing AS MATERIALIZED (
                    SELECT nexus_attention_preferences_v1(o.item,p.seen_at,p.snoozed_until,p.revision,:now) AS item
                    FROM occurrences o LEFT JOIN attention_preferences p
                    ON p.principal='operator' AND p.attention_id=json_extract(o.item,'$.attention_id')),
                filtered AS MATERIALIZED (SELECT item FROM viewing WHERE ''' + (' AND '.join(clauses) or '1') + ') '
            if interrupt():
                raise OktoNexusError('ATTENTION_QUERY_BUDGET',
                    'The attention query exceeded its processing budget. Narrow the filters and refresh; no empty snapshot is inferred.', {})
            yield relation, params
        except sqlite3.Error as error:
            if expired:
                raise OktoNexusError('ATTENTION_QUERY_BUDGET',
                    'The attention query exceeded its processing budget. Narrow the filters and refresh; no empty snapshot is inferred.', {}) from None
            raise OktoNexusError(ErrorCode.DB_ERROR, 'The attention projection could not be read.', {}) from error
        finally:
            conn.set_progress_handler(None, 0)
            if registered:
                # Pooled connections must not retain the request's authority/config.
                conn.create_function('nexus_attention_project_v1', 3, None)
                conn.create_function('nexus_attention_preferences_v1', 5, None)
                conn.create_aggregate('nexus_attention_set_digest_v1', 1, None)
                for name, arity, _ in functions:
                    conn.create_function(name, arity, None)

    def snapshot(self, uow, *, filters, now, config, access, context, after=None, limit=50):
        with self._relation(uow, filters=filters, now=now, config=config, access=access, context=context) as (sql, params):
            conn = uow.connection
            aggregate = conn.execute(sql + '''SELECT COUNT(*) AS total,
                COUNT(DISTINCT json_extract(item,'$.attention_id')) AS unique_episodes,
                nexus_attention_set_digest_v1(item) AS revision,
                SUM(json_extract(item,'$.category')='action_required') AS action_required,
                SUM(json_extract(item,'$.category')='watch') AS watch,
                SUM(json_extract(item,'$.priority')=10) AS p10,
                SUM(json_extract(item,'$.priority')=20) AS p20,
                SUM(json_extract(item,'$.priority')=30) AS p30,
                SUM(json_extract(item,'$.seen_state.seen')=0) AS unseen,
                SUM(json_extract(item,'$.seen_state.snoozed')=1) AS snoozed,
                (SELECT MIN(CASE WHEN json_extract(item,'$.next_change_at')>:now
                    THEN json_extract(item,'$.next_change_at') END) FROM viewing) AS next_change_at
                FROM filtered''', params).fetchone()
            if aggregate['unique_episodes'] != aggregate['total']:
                raise OktoNexusError(ErrorCode.DB_ERROR, 'The attention source returned duplicate episode references.', {})
            revision = aggregate['revision'] or _SetDigest().finalize()
            if after is not None and after['snapshot_revision'] != revision:
                raise OktoNexusError(ErrorCode.CONFLICT, 'Attention changed while paging. Refresh the snapshot.',
                                     {'reason': 'ATTENTION_SNAPSHOT_CHANGED'})
            rows = []
            if limit:
                params['page_limit'] = limit + 1
                clause = ''
                if after is not None:
                    params.update(after_priority=after['after'][0], after_first=after['after'][1], after_id=after['after'][2])
                    clause = '''WHERE json_extract(item,'$.priority')<:after_priority OR
                        (json_extract(item,'$.priority')=:after_priority AND
                         (json_extract(item,'$.first_detected_at')>:after_first OR
                          (json_extract(item,'$.first_detected_at')=:after_first AND
                           json_extract(item,'$.attention_id')>:after_id)))'''
                rows = [json.loads(row[0]) for row in conn.execute(sql + 'SELECT item FROM filtered ' + clause + '''
                    ORDER BY json_extract(item,'$.priority') DESC,
                             json_extract(item,'$.first_detected_at'),json_extract(item,'$.attention_id')
                    LIMIT :page_limit''', params)]
            cursor = conn.execute("SELECT COALESCE((SELECT seq FROM sqlite_sequence WHERE name='events'),0),"
                                  '(SELECT MIN(event_id) FROM events)').fetchone()
            return dict(items=rows, total=aggregate['total'],
                snapshot_revision=revision,
                counts=dict(action_required=aggregate['action_required'] or 0, watch=aggregate['watch'] or 0,
                    priority={'10':aggregate['p10'] or 0, '20':aggregate['p20'] or 0, '30':aggregate['p30'] or 0},
                    unseen=aggregate['unseen'] or 0, snoozed=aggregate['snoozed'] or 0),
                event_cursor=int(cursor[0]), event_low_watermark=cursor[1], next_change_at=aggregate['next_change_at'])

    def get(self, uow, *, attention_id, now, config, access, context):
        filters = dict(state='all', seen='all')
        with self._relation(uow, filters=filters, now=now, config=config, access=access, context=context) as (sql, params):
            params['attention_id'] = attention_id
            rows = uow.connection.execute(sql + "SELECT item FROM filtered WHERE json_extract(item,'$.attention_id')=:attention_id LIMIT 2", params).fetchall()
            if len(rows) > 1:
                raise OktoNexusError(ErrorCode.DB_ERROR, 'The attention source returned duplicate episode references.', {})
            return json.loads(rows[0][0]) if rows else None

    def save_preference(self, uow, *, attention_id, seen_at, snoozed_until, expected_revision, now):
        conn = uow.connection
        if expected_revision == 0:
            changed = conn.execute('''INSERT INTO attention_preferences
                (principal,attention_id,seen_at,snoozed_until,revision,updated_at)
                VALUES ('operator',?,?,?,1,?) ON CONFLICT(principal,attention_id) DO NOTHING''',
                (attention_id, seen_at, snoozed_until, now)).rowcount
        else:
            changed = conn.execute('''UPDATE attention_preferences SET seen_at=?,snoozed_until=?,
                revision=revision+1,updated_at=? WHERE principal='operator' AND attention_id=? AND revision=?''',
                (seen_at, snoozed_until, now, attention_id, expected_revision)).rowcount
        if changed != 1:
            raise OktoNexusError(ErrorCode.CONFLICT, 'The viewing preference changed. Refresh the occurrence.',
                                 {'reason': 'ATTENTION_PREFERENCE_CHANGED'})
