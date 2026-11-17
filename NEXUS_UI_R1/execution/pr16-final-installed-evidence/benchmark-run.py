"""Finite installed-package SQLite qualification; no provider/native/browser.

Reuses the existing synthetic read-fact fixture and volume seed, never changes
the installed prefix or source product. Outputs only beside this script.
"""

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time

from okto_nexus.application.home_entries import HomeEntriesService
from okto_nexus.adapters.outbound.sqlite.home_entries import SqliteHomeEntryRelations
from okto_nexus.adapters.outbound.sqlite.resource_pool import SQLiteInstancePool
from okto_nexus.domain.resource_pool import PoolInstance
import okto_nexus

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))  # fixture imports only; product must remain installed


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


old = load('ui022_measure_offline', REPO/'NEXUS_UI_R1/execution/pr03-performance/measure.py')


def save(name, value):
    path = HERE/name
    assert not path.exists(), 'Never overwrite a live/previous campaign result'
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy_session(c, original, sid, lifecycle='READY'):
    opening = c.execute('SELECT * FROM execution_operations WHERE operation_id=?',
                        (original['open_operation_id'],)).fetchone()
    scope = dict(json.loads(opening['expected_revisions_json']), session_id=sid)
    old.fixtures._copy(c, 'execution_operations', opening, operation_id=sid+'-open',
                      session_id=sid, expected_revisions_json=json.dumps(scope))
    old.fixtures._copy(c, 'execution_sessions', original, session_id=sid,
                      open_operation_id=sid+'-open', lifecycle_state=lifecycle,
                      stream_epoch=sid+'-epoch')
    return opening


def all_entries(service, s):
    page = service.read(context=s.operator, filters={'quick':'all'}, limit=100, preview=100)
    assert page['status'] == 'ready', page
    return page, [e for g in page['items'] for e in g['children']]


def semantics(s):
    service = HomeEntriesService(s.app.state.home, queries=SqliteHomeEntryRelations())
    baseline, before = all_entries(service, s)
    with s.factory.unit_of_work() as uow:
        c = uow.connection
        original = c.execute('SELECT * FROM execution_sessions WHERE session_id=?', (s.sessions[0],)).fetchone()
        for sid, lifecycle in [('data-ready','READY'), ('data-opening','OPENING'),
                               ('data-warm','READY'), ('data-cleanup','CLOSING')]:
            opening = copy_session(c, original, sid, lifecycle)
            if sid == 'data-warm':
                SQLiteInstancePool(c).add(PoolInstance('data-warm-slot', 'subject',
                    original['executor_id'], 'synthetic-read-configuration', 'WARM',
                    s.clock.now_epoch(), resource_id=sid))
            if sid == 'data-cleanup':
                c.execute("INSERT INTO execution_session_containment(server_id,executor_id,session_id,owner_generation,opening_operation_id,opening_intent_hash,request_json,state,recorded_at) VALUES(?,?,?,1,?,?,'{}','REQUESTED',?)",
                    (original['server_id'], original['executor_id'], sid, sid+'-open', opening['intent_hash'], s.clock.now_iso()))
        assert c.execute("SELECT COUNT(*) FROM execution_operations WHERE action='turn.submit' AND session_id LIKE 'data-%'").fetchone()[0] == 0
        assert SQLiteInstancePool(c).get('data-warm-slot').state == 'WARM'
    page, entries = all_entries(service, s)
    passive = [e for e in entries if e['kind']=='session' and e['target']['session_id'].startswith('data-')]
    assert len(passive) == 4
    assert all(e['display_state'] != 'running' and 'operation_id' not in e['target'] for e in passive)
    assert page['summary']['activities'] == baseline['summary']['activities']
    assert sum(e['kind']=='work' and e['display_state']=='running' for e in entries) == sum(e['kind']=='work' and e['display_state']=='running' for e in before)
    # Link the existing real-schema SUCCEEDED receipt to the exact OPEN handoff.
    # Keep cleanup REQUESTED on the success session. These are synthetic durable
    # read facts, not an assertion that a native turn was actually executed.
    with s.factory.unit_of_work() as uow:
        c, now = uow.connection, s.clock.now_iso()
        c.execute("INSERT INTO delivery_outbox(operation_id,delivery_id,message_id,workspace_id,actor_agent_id,credential_binding,recipient_agent_id,endpoint_id,endpoint_revision,envelope,request_hash,authorization_revision,root_operation_id,created_at,updated_at) VALUES('data-domain','ui-delivery-0','ui-message-0','ws','subject','fixture','B','ep',1,'{}','fixture','fixture','data-domain',?,?)", (now, now))
        grant = c.execute('SELECT grant_id FROM runtime_execution_grants LIMIT 1').fetchone()[0]
        c.execute("UPDATE handoffs SET claim_epoch=1 WHERE handoff_id='ui-handoff-0'")
        c.execute("INSERT INTO runtime_handoff_bindings(handoff_id,claim_epoch,operation_id,grant_id,grant_revision,actor_agent_id,idempotency_key,request_hash,created_at) VALUES('ui-handoff-0',1,'data-domain',?,1,'subject','data-read-fact','fixture',?)", (grant, now))
        c.execute("INSERT INTO execution_domain_deliveries(server_id,executor_id,operation_id,domain_operation_id) VALUES(?,?,'ui-success','data-domain')", (original['server_id'],original['executor_id']))
        assert c.execute("SELECT status FROM handoffs WHERE handoff_id='ui-handoff-0'").fetchone()[0]=='OPEN'
        assert c.execute("SELECT stage FROM execution_receipts WHERE operation_id='ui-success'").fetchone()[0]=='SUCCEEDED'
    linked, entries = all_entries(service, s)
    parent = next(e for e in entries if e['source_ref']['id']=='ui-handoff-0')
    result = next(r for r in parent['results_preview'] if r['detail_target'].get('operation_id')=='ui-success')
    assert parent['display_state'] != 'completed'
    assert result['outcome']=='SUCCEEDED' and result['cleanup_state']=='pending'
    assert all(action['kind'] in ('inspect','attention') for action in parent['actions'])
    # Read model exposes no productive replay action; work authorization is a
    # separate explicit surface and is deliberately not invoked here.
    return {'status':'PASS', 'T-DATA-12':{'passive_sessions':passive,
        'summary_before':baseline['summary'],'summary_after':page['summary'],
        'warm_pool_state':'WARM', 'cleanup_containment':'REQUESTED', 'turns_for_four_sessions':0},
        'T-DATA-14':{'handoff_status':'OPEN','entry':parent,'result':result,
        'productive_replay_action_exposed':False},
        'limits':'SQLite synthetic persisted facts; no browser copy/interaction or native lifecycle qualification; READY/OPENING/WARM/CLOSING are not productive evidence.'}


def measured(service, s, kwargs):
    with old.tracing(s.factory) as trace:
        page = service.read(context=s.operator, filters={'workspace_id':'perf-ws','quick':'all'}, **kwargs)
    assert page['status']=='ready', page
    statements = trace.pop('statements')
    forbidden = [sql for sql in statements if 'event_journal' in sql.lower() or 'transcript' in sql.lower()]
    assert not forbidden
    assert trace['writes']==0 and trace['uows']==[{'write':False}]
    return page, dict(trace, sql_statements=len(statements), sql_sha256=hashlib.sha256('\n'.join(statements).encode()).hexdigest(),
                     transcript_or_journal_reads=0, payload_bytes=old.size(page))


def dataset(n):
    own = Path(tempfile.mkdtemp(prefix='nexus-ui-r1-offline-'))
    report = {'own_temp':str(own), 'agents':n}
    with old.fixtures.scenario(own) as s:
        report['volume'] = old.seed(s,n,0)
        service = HomeEntriesService(s.app.state.home,queries=SqliteHomeEntryRelations())
        initial = service.read(context=s.operator,filters={'workspace_id':'perf-ws','quick':'all'})
        assert initial['status']=='ready' and initial['total']==n
        group = initial['items'][0]
        entry = group['children'][0]
        assert entry['sessions_total']==1
        variants = {'entries':{}, 'children':{'partition':'children','group_id':group['id'],'cursor':group['children_cursor']},
                    'sessions':{'partition':'sessions','group_id':group['id'],'entry_id':entry['id']}}
        for name, kwargs in variants.items():
            _, instrument = measured(service,s,kwargs)
            service.read(context=s.operator,filters={'workspace_id':'perf-ws','quick':'all'},**kwargs)
            samples=[]
            for _ in range(3):
                start=time.perf_counter()
                page=service.read(context=s.operator,filters={'workspace_id':'perf-ws','quick':'all'},**kwargs)
                samples.append((time.perf_counter()-start)*1000)
                assert page['status']=='ready'
                assert 'private-marker' not in json.dumps(page)
            report[name]={'instrumentation':instrument,'samples_ms':samples,'p50_ms':statistics.median(samples),
                          'nearest_rank_p95_ms':sorted(samples)[math.ceil(.95*len(samples))-1]}
        if n==1:
            report['semantics']=semantics(s)
    report['cleanup']='Own fixture WSS/lifespan/factory context exited normally; no browser, native CLI or server process launched.'
    report['status']='PASS'
    save(f'agents-{n}.json',report)
    print(json.dumps({'agents':n,'status':'PASS','sql':{k:report[k]['instrumentation']['sql_statements'] for k in variants}}),flush=True)
    return report


def main():
    origin=Path(okto_nexus.__file__).resolve()
    assert origin.is_relative_to(Path(sys.prefix).resolve()), origin
    sources=[Path(okto_nexus.__file__).resolve().parent/p for p in ('application/home_entries.py','domain/home_entries.py','domain/home_entry_pages.py','adapters/outbound/sqlite/home_entries.py','adapters/outbound/sqlite/home.py')]
    sources += [Path(__file__), REPO/'NEXUS_UI_R1/execution/pr03-performance/measure.py', REPO/'NEXUS_UI_R1/execution/fixtures.py']
    pins={str(p):sha(p) for p in sources}
    reports=[dataset(n) for n in (1,10,100)]
    drift=[p for p,value in pins.items() if sha(p)!=value]
    assert not drift, drift
    counts={kind:[r[kind]['instrumentation']['sql_statements'] for r in reports] for kind in ('entries','children','sessions')}
    assert all(len(set(value))==1 for value in counts.values()), counts
    save('qualification.json', {'status':'PASS_OFFLINE_SCOPED', 'tests':['T-PERF-01','T-DATA-12','T-DATA-14'],
        'python':sys.version,'python_executable':sys.executable,'product_origin':str(origin), 'platform':platform.platform(),
        'cpu_count':os.cpu_count(),'sqlite':__import__('sqlite3').sqlite_version,'source_pins':pins,'source_drift':drift,
        'sql_counts_by_agents_1_10_100':counts,'latency_scope':'HomeEntriesService.read only;3warm samples+1warmup per series;not HTTP/browser/SLO',
        'provider_or_native_invoked':False,'installed_prefix_modified':False,'limits':['Synthetic SQLite durable read facts; no native lifecycle/billing claim.',
        'Warm/cleanup technical facts are not projected as activity; this does not qualify browser labels.',
        'Three samples only diagnose query-growth, not production latency percentiles. Existing PR03 larger benchmark retained.'],
        'files_sha256':{f'agents-{n}.json':sha(HERE/f'agents-{n}.json') for n in (1,10,100)}})


if __name__=='__main__':
    main()
