"""Finite UI022 service benchmark; own SQLite fixtures, never a provider.

Run from repository: rtk proxy .venv/Scripts/python.exe -X utf8
  NEXUS_UI_R1/execution/pr03-performance/measure.py
"""
from contextlib import contextmanager
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from okto_nexus.application.home_entries import HomeEntriesService
from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations

spec = importlib.util.spec_from_file_location('ui022_fixture', ROOT / 'NEXUS_UI_R1/execution/fixtures.py')
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixtures
spec.loader.exec_module(fixtures)


class Explained(SqliteHomeEntryRelations):
    def __init__(self):
        super().__init__()
        self.plans = []

    def explain(self, uow, sql, params, name):
        self.plans.append(dict(name=name, sql=sql, parameters=params,
            plan=[dict(x) for x in uow.connection.execute('EXPLAIN QUERY PLAN ' + sql, params)]))

    def _project(self, uow, **kw):
        if kw['attention_relation'] is None:
            ctes, additions = 'WITH home_attention AS MATERIALIZED (SELECT NULL AS item WHERE 0)', {}
        else:
            ctes, additions = self.home._attention_relations(kw['attention_relation'])
        sql = ctes + ',' + kw['relation'].lstrip()[4:] + ' SELECT item FROM filtered'
        self.explain(uow, sql, dict(kw['params'], **additions), 'work_or_results')
        return super()._project(uow, **kw)

    def _rows(self, uow, sql, params, check_budget=None):
        self.explain(uow, sql, params, 'context_or_correlation')
        return super()._rows(uow, sql, params, check_budget)

    def _attention(self, uow, relation, check_budget=None):
        sql, params = relation
        self.explain(uow, sql + ' SELECT item FROM filtered', params, 'attention')
        return super()._attention(uow, relation, check_budget)


def seed(s, n, events):
    """Synthetic persisted read facts, not admissions or native executions."""
    with s.factory.unit_of_work() as uow:
        c, now = uow.connection, s.clock.now_iso()
        row = lambda table, where='': c.execute('SELECT * FROM ' + table + ' ' + where).fetchone()
        fixtures._copy(c, 'workspaces', row('workspaces', "WHERE workspace_id='ws'"), workspace_id='perf-ws')
        wxb = row('execution_workspace_bindings', "WHERE workspace_binding_id='wxb'")
        fixtures._copy(c, 'execution_workspace_bindings', wxb, workspace_binding_id='perf-wxb', workspace_id='perf-ws')
        agent = row('agents', "WHERE agent_id='subject'")
        endpoint = row('agent_endpoints', "WHERE endpoint_id='ep'")
        binding = row('execution_bindings', "WHERE binding_id='binding'")
        session = row('execution_sessions', 'WHERE session_id=' + "'" + s.sessions[0] + "'")
        opening = row('execution_operations', "WHERE action='runtime.open'")
        turn = row('execution_operations', "WHERE action='turn.submit'")
        for i in range(n):
            aid, eid, bid, sid = (f'perf-{p}-{i:03}' for p in ('agent', 'ep', 'binding', 'session'))
            fixtures._copy(c, 'agents', agent, agent_id=aid, api_key_hash=f'own-benchmark-{i}')
            fixtures._copy(c, 'agent_endpoints', endpoint, endpoint_id=eid, workspace_id='perf-ws', agent_id=aid)
            fixtures._copy(c, 'execution_bindings', binding, binding_id=bid, endpoint_id=eid, workspace_binding_id='perf-wxb')
            scope = dict(json.loads(opening['expected_revisions_json']), binding_id=bid,
                workspace_id='perf-ws', workspace_binding_id='perf-wxb', session_id=sid)
            shared = dict(binding_id=bid, workspace_binding_id='perf-wxb', workspace_id='perf-ws', session_id=sid,
                subject_agent_id=aid, expected_revisions_json=json.dumps(scope))
            fixtures._copy(c, 'execution_operations', opening, operation_id=sid+'-open', **shared)
            fixtures._copy(c, 'execution_sessions', session, session_id=sid, binding_id=bid,
                workspace_binding_id='perf-wxb', workspace_id='perf-ws', open_operation_id=sid+'-open', stream_epoch=sid+'-epoch')
            for j in range(10):
                oid = f'perf-turn-{i:03}-{j:02}'
                fixtures._copy(c, 'execution_operations', turn, operation_id=oid, **shared)
                c.execute("INSERT INTO execution_receipts(server_id,executor_id,operation_id,receipt_revision,intent_hash,stage,possible_effect,retry_safe,received_at) VALUES(?,?,?,1,?,'SUBMITTED',1,0,?)",
                    (turn['server_id'], turn['executor_id'], oid, turn['intent_hash'], now))
        # Valid vocabulary, synthetic durable volume. Entries reads bounds, not replay.
        if events:
            from okto_nexus.domain.events import validate_emit_vocabulary
            validate_emit_vocabulary(stream='workspace', type='message.created', visibility='public')
            c.executemany("INSERT INTO events(workspace_id,stream,type,actor_agent_id,payload,visibility,target,created_at) VALUES('perf-ws','workspace','message.created','perf-agent-000',?,'public',NULL,?)",
                ((json.dumps({'benchmark_synthetic': True, 'ordinal': i}), now) for i in range(events)))
        return dict(agents=n, activities=n*10, added_events=events,
            total_events=c.execute('SELECT COUNT(*) FROM events').fetchone()[0])


@contextmanager
def tracing(factory):
    original, current = factory.unit_of_work, threading.get_ident()
    report = dict(statements=[], uows=[], writes=0)
    @contextmanager
    def traced(*args, **kwargs):
        with original(*args, **kwargs) as uow:
            if threading.get_ident() != current:
                yield uow
                return
            report['uows'].append(kwargs)
            c, before = uow.connection, uow.connection.total_changes
            c.set_trace_callback(report['statements'].append)
            try:
                yield uow
            finally:
                report['writes'] += c.total_changes-before
                c.set_trace_callback(None)
    factory.unit_of_work = traced
    try:
        yield report
    finally:
        factory.unit_of_work = original


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())


def stats(samples):
    times = sorted(x['milliseconds'] for x in samples)
    return dict(samples=samples, p50_ms=statistics.median(times),
        nearest_rank_p95_ms=times[math.ceil(.95*len(times))-1],
        max_payload_bytes=max(x['payload_bytes'] for x in samples))


def dataset(n, samples):
    home = Path(tempfile.mkdtemp(prefix='nexus-ui022-'))
    result = dict(own_temp_home=str(home), cleanup='pending')
    try:
        with fixtures.scenario(home) as s:
            result['volume'] = seed(s, n, 100000 if n == 100 else 0)
            service = HomeEntriesService(s.app.state.home, queries=SqliteHomeEntryRelations())
            def read(**kw):
                return service.read(context=s.operator, filters={'workspace_id':'perf-ws','quick':'all'}, **kw)
            started = time.perf_counter()
            first = read()
            result['first_read_ms'] = (time.perf_counter()-started)*1000
            result['first_status'] = first['status']
            result['source_status'] = first['source_status']
            assert first['status'] == 'ready', first
            assert first['total'] == n, first['total']
            assert first['summary']['activities']['value'] == n*10, first['summary']
            group = first['items'][0]
            assert group['children_total'] == 10 and len(group['children']) == 3
            # Instrumentation is separate from latency samples.
            with tracing(s.factory) as trace:
                traced = read()
            statements = trace.pop('statements')
            result['instrumentation'] = dict(trace, sql_statements=len(statements),
                sql=statements, payload_bytes=size(traced),
                transcript_or_journal_read=any('event_journal' in x.lower() or 'transcript' in x.lower() for x in statements))
            assert trace['writes'] == 0 and trace['uows'] == [{'write': False}]
            assert not result['instrumentation']['transcript_or_journal_read']
            for name, kw in [('groups',{}), ('children',dict(partition='children',group_id=group['id'],cursor=group['children_cursor']))]:
                raw = []
                read(**kw)  # Explicit unmeasured warmup.
                for _ in range(samples):
                    t = time.perf_counter()
                    page = read(**kw)
                    elapsed = (time.perf_counter()-t)*1000
                    raw.append(dict(milliseconds=elapsed,status=page['status'],payload_bytes=size(page),items=len(page['items'])))
                    assert page['status'] == 'ready', page
                result[name] = stats(raw)
            ids, cursor, pages = [], None, 0
            while True:
                page = read(cursor=cursor)
                assert page['status'] == 'ready'
                ids.extend(g['id'] for g in page['items'])
                pages += 1
                cursor = page['next_cursor']
                if not cursor:
                    break
            child = read(partition='children',group_id=group['id'],cursor=group['children_cursor'])
            child_ids = [x['id'] for x in group['children']+child['items']]
            assert len(ids) == len(set(ids)) == n
            assert len(child_ids) == len(set(child_ids)) == 10
            assert not child['has_more']
            result['paging'] = dict(groups=len(ids),group_pages=pages,unique=True,children=len(child_ids),children_pages=2)
            q = Explained()
            explained = HomeEntriesService(s.app.state.home, queries=q).read(context=s.operator,
                filters={'workspace_id':'perf-ws','quick':'all'})
            assert explained['status'] == 'ready'
            result['explain'] = q.plans
            # SUBMITTED receipts and READY sessions never manufacture productive running.
            entries = group['children'] + child['items']
            result['submitted_states'] = sorted({e['display_state'] for e in entries})
            assert 'running' not in result['submitted_states']
        result['cleanup'] = 'fixture context exited; WSS/lifespan generator closed; connection factory closed; no server/browser/provider process created'
        result['status'] = 'PASS'
    except Exception as error:
        result.update(status='FAIL',error=repr(error))
        raise
    finally:
        (OUT / f'agents-{n}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--agents',type=int,nargs='+',default=[1,10,100])
    p.add_argument('--samples',type=int,default=20)
    args = p.parse_args()
    files = ['src/okto_nexus/application/home_entries.py','src/okto_nexus/domain/home_entry_pages.py',
        'src/okto_nexus/domain/home_entries.py','src/okto_nexus/adapters/outbound/sqlite/home_entries.py',
        'src/okto_nexus/adapters/outbound/sqlite/home.py','src/okto_nexus/application/home.py',
        'src/okto_nexus/adapters/outbound/sqlite/attention.py','NEXUS_UI_R1/execution/fixtures.py',
        str(Path(__file__).relative_to(ROOT)).replace('\\','/')]
    metadata = dict(python=sys.version,sqlite=sqlite3.sqlite_version,system=platform.system(),
        release=platform.release(),machine=platform.machine(),processor=platform.processor(),cpus=os.cpu_count(),
        clock='perf_counter; service.read only',warmup_per_series=1,samples=args.samples,
        source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files})
    (OUT/'environment.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    for n in args.agents:
        value = dataset(n,args.samples)
        print(json.dumps(dict(agents=n,status=value['status'],groups=value['groups']['p50_ms'],
            p95=value['groups']['nearest_rank_p95_ms'],sql=value['instrumentation']['sql_statements'])),flush=True)


if __name__ == '__main__':
    main()
