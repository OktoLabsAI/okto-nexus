from pathlib import Path
from datetime import datetime, timezone
import subprocess, json, hashlib, sys, time

H = Path(__file__).resolve().parent
B = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7')
SID = 'ses_8bc0449b68998cfe91ec1a2df9319d23'
OPS = {'op_772cf5101f12f73b1acc75daefe6b98c', 'op_37e2ddb1ba2d183c899606a846396bb3'}
argv = [sys.executable, '-I', '-B', '-X', 'utf8', '-m',
        'okto_nexus.adapters.inbound.cli.main', 'work', 'status',
        '--home', str(B/'campaign/operator-home'), '--profile', 'm1-sonnet-remote-recovery02',
        '--operator-profile', 'm1-sonnet-human', '--project', str(B), '--session-id', SID, '--json']
started = datetime.now(timezone.utc).isoformat(); clock = time.monotonic()
r = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
for name, raw in [('reopen-status.raw.json', r.stdout), ('reopen-status.stderr', r.stderr)]:
    with (H/'paid-work/private'/name).open('xb') as f: f.write(raw)
assert r.returncode == 0
v = json.loads(r.stdout)
assert v['session']['scope']['session_id'] == SID
events = v['events']['events']
results = [{'operation_id': e['operation_id'], 'sequence': e['sequence'],
            'received_at': e['received_at'], 'native_type': e['native_type'],
            'output_text': e['payload'].get('output_text'),
            'delivery_outcome': e['payload'].get('delivery_outcome')}
           for e in events if e.get('operation_id') in OPS and e['native_type'] == 'result:success']
assert {x['operation_id'] for x in results} == OPS
assert next(x for x in results if x['operation_id']=='op_37e2ddb1ba2d183c899606a846396bb3')['output_text'] == 'The reported sum is **10**.'
decision = v['decision']
assert decision['canonical_state']=='CONFIRMED' and decision['actor_agent_id']=='operator'
assert decision['approval_key']['session_id']==SID
p = {'status':'REOPENED_CLI_CANONICAL_RESULTS_CONFIRMED', 'started_utc':started,
     'finished_utc':datetime.now(timezone.utc).isoformat(), 'elapsed_seconds':time.monotonic()-clock,
     'returncode':r.returncode, 'session_id':SID, 'scope':v['session']['scope'],
     'session_observation':{k:v['session'].get(k) for k in ('lifecycle_state','process_state','ownership','lease_state')},
     'results':results, 'decision':{k:decision[k] for k in ('decision_id','canonical_state','actor_agent_id','native_decision','native_stage')},
     'event_page':{k:v['events'].get(k) for k in ('stream_epoch','next_after_sequence','committed_contiguous','gap_pending','has_more')},
     'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(), 'raw_stdout_public':False,
     'cli_action':'work status --session-id', 'new_provider_requests':0}
with (H/'paid-work/public/cli-reopen-proof.json').open('x', encoding='utf-8') as f:
    json.dump(p,f,ensure_ascii=False,indent=2); f.write('\n')
print(json.dumps({'status':p['status'],'returncode':0,'canonical_results':len(results),'continuation':'The reported sum is **10**.','new_provider_requests':0}))
