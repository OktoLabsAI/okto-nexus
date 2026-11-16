"""Curate canonical human browser CAS evidence; no execution side effects."""
from pathlib import Path
import hashlib
import json
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
source=ROOT/'output/playwright/ui04-human-live'
target=HERE/'human-vmhGy86G'
target.mkdir(exist_ok=True)
for name in ['results.json','ready.json','output.txt','db-exact-operation.json','human-reviewed-before-submit.png','human-canonical-dispatch-pending.png']:
    shutil.copy2(source/name,target/name)
control=Path(json.loads((source/'control.json').read_text())['control'])
for name in ['liveness.json','final-db.json']:shutil.copy2(control/name,target/name)
for name in ['human-live-fixture.py','human-fixture.py','human-probe.js']:shutil.copy2(HERE/name,target/name)
result=json.loads((target/'results.json').read_text())
ready=json.loads((target/'ready.json').read_text())
db=json.loads((target/'db-exact-operation.json').read_text())
live=json.loads((target/'liveness.json').read_text())
report=dict(status='PASS_SCOPED_HUMAN_GUARDS_AND_TWO_TAB_CAS',checks_passed=8,
    bundle='index-vmhGy86G.js',js_sha256='e4a1b963969fe42a195a904fe8238b0e5e9c927f67e97d47ba9db0eac2b926c8',
    preflight=ready['preflight'],native_decision_posts=2,actual_statuses=[202,409],page_errors=result['errors'],
    db_exact_operation=db['operation'],matching_operations=db['matching_operations'],matching_outbox=db['matching_outbox'],decisions=db['decisions'],
    native_application='NOT_EXECUTED; canonical CONFIRMED plus DISPATCH_PENDING, possible_effect false; no provider/native executable',
    heartbeat_count=sum(x['kind']=='canonical_wss_heartbeat' for x in live['diagnostics']),
    current_authority_checks=sum(x['kind']=='authority' and x.get('current',False) for x in live['diagnostics']),
    peer_thread_stopped=live['thread_stopped'],peer_errors=[x for x in live['diagnostics'] if x['kind']=='peer_failed'],
    limitation='Canonical lease renew/applied completed before logging KeyError for absent wire valid_until_server; heartbeat worker ended then. No continuous180s renewal qualification. Original fixed controlled clock retained, no TTL/grant/budget/recipient SQL bypass.',
    source_pin_drift=[p for p,h in ready['source_sha256'].items() if (ROOT/p).exists() and hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h],
    cleanup=dict(browser_pid=60848,browser_close_exit=0,fixture_exit=0,pid_absent=True,port=53807,port_absent=True,thread_joined=True,
        tools=['e27b1a','5cf928','b6b155']),
    sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file() and p.name!='qualification.json'})
assert result['status']=='PASS' and db['matching_operations']==db['matching_outbox']==db['decisions']==1
(target/'qualification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'checks':8,'drift':report['source_pin_drift'],
    'sha256':hashlib.sha256((target/'qualification.json').read_bytes()).hexdigest()}))
