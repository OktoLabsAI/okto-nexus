from pathlib import Path
from datetime import datetime
import hashlib
import json
import shutil
import sqlite3

here=Path(__file__).resolve().parent
root=here.parents[3]
out=root/'output/playwright/r3-harness-board'
control=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-r3-harness-control-t455pd9d')
dest=here/'final'
dest.mkdir(exist_ok=True)
for name in ('ready.json','actions.json','cleanup.json','peer-status.json','parallel-added.json'):
    shutil.copy2(control/name,dest/name)
for name in ('phase1.js','phase2.js','phase1-result.json','phase2-result.json','runtime-pins.json','phase1-desktop.png','phase2-desktop.png','phase2-mobile-active.png','phase2-mobile-needs_you.png','phase2-mobile-results.png','add-get-only.png'):
    shutil.copy2(out/name,dest/name)
first=json.loads((dest/'phase1-result.json').read_text())
second=json.loads((dest/'phase2-result.json').read_text())
assert [c['status'] for c in first['checks']]==['PASS']*5+['FAIL']
assert second['status']=='PASS' and len(second['checks'])==9 and all(c['status']=='PASS' for c in second['checks'])
assert first['pageErrors']==[] and second['pageErrors']==[] and second['consoleErrors']==[]
assert first['consoleErrors']==['Failed to load resource: net::ERR_CONNECTION_REFUSED']
obsolete=[r for r in first['requests'] if ':60106/' in r['url']]
assert len(obsolete)==1 and all(r['method']=='GET' for r in first['requests']+second['requests'])
pins=json.loads((dest/'runtime-pins.json').read_text())
drift=[p for p,h in pins.items() if hashlib.sha256((root/p).read_bytes()).hexdigest()!=h]
assert not drift,drift
prior=here.parent/'pr15-human-third-prepare'
prior_pins=json.loads((here/'pr15-manifest-copy.json').read_text())
prior_drift=[p for p,h in prior_pins.items() if hashlib.sha256((prior/p).read_bytes()).hexdigest()!=h]
assert not prior_drift,prior_drift
ready=json.loads((dest/'ready.json').read_text())
conn=sqlite3.connect((Path(ready['home'])/'home/nexus.db').as_uri()+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
native=[dict(r) for r in conn.execute('SELECT canonical_request_id,received_at,expires_at,session_id FROM execution_native_requests')]
facts={'bindings':[dict(r) for r in conn.execute('SELECT binding_id,binding_revision FROM execution_bindings')],
       'setup_commits':conn.execute('SELECT count(*) FROM connection_setup_commits').fetchone()[0],
       'proposed_add_agents_persisted':conn.execute("SELECT count(*) FROM agents WHERE agent_id LIKE 'project_%'").fetchone()[0],
       'original_grants_preserved':all(dict(conn.execute('SELECT grant_id,expires_at,max_executions FROM runtime_execution_grants WHERE grant_id=?',(g['grant_id'],)).fetchone())==g for g in ready['original_grants']),
       'lane_ticket_expiries':[dict(r) for r in conn.execute('SELECT l.binding_id,t.expires_at AS lane_ticket_expires_at FROM execution_control_lanes l JOIN execution_link_tickets t ON t.ticket_id=l.ticket_id')],
       'native_requests':native,
       'parallel_operation':dict(conn.execute("SELECT operation_id,session_id,binding_id,action FROM execution_operations WHERE operation_id='r3-parallel-operation'").fetchone()),
       'public_handoff':dict(conn.execute("SELECT handoff_id,status,claimed_by,verify_by,visibility FROM handoffs WHERE handoff_id='r3-operator-handoff'").fetchone())}
conn.close()
assert facts['setup_commits']==0 and facts['proposed_add_agents_persisted']==0 and facts['original_grants_preserved']
assert facts['lane_ticket_expiries']==ready['decision_authority_times']
instant=lambda s:datetime.fromisoformat(s.replace('Z','+00:00'))
assert len(native)==1 and (instant(native[0]['expires_at'])-instant(native[0]['received_at'])).total_seconds()==120
assert instant(second['board']['generated_at'])<instant(native[0]['expires_at'])
functional=first['checks'][:5]+second['checks']
qualification={
 'status':'FOCUSED_TWO_PHASES_QUALIFIED_WITH_CLASSIFIED_HARNESS_ANTECEDENTS_NO_HUMAN_PASS',
 'functional_checks_pass':14,'functional_checks':functional,
 'first_phase_raw_status':first['status'],
 'first_phase_failed_environment_guard':{'assertion':first['checks'][-1],'console_errors':first['consoleErrors'],'obsolete_origin_requests':obsolete,'classification':'Reused own CLI page made one request to prior closed fixture60106 before navigation. Obsolete origin and refused listener are proven in raw logs/8156c5. No current-origin non200 response, page exception or mutation was recorded. Raw failed guard is preserved, not converted to PASS.'},
 'second_phase_raw_status':second['status'],'second_phase_console_errors':second['consoleErrors'],
 'source_sha256':pins,'source_pin_drift':drift,'prior_pr15_pin_drift':prior_drift,
 'root_validation_reference':'NEXUS_UI_R1/execution/pr26c-harness-frontend-complete/qualification.json; root reported350/350Node and TSC/Vite PASS.',
 'facts':facts,'phase2_snapshot_generated_at':second['board']['generated_at'],
 'scope':'Real Chromium and canonical HTTP/SQLite projection using owned inert mock peer. First input is canonical admitted mock-Core/WSS ingress; parallel operation and terminal history are explicitly synthetic read facts, not real provider/native execution.',
 'limits':[
  'The two observed states are sequential on the same original registered binding: initially blocked, then working with an independent pending request after a parallel RUNNING read fact. This does not prove two native harnesses executing simultaneously.',
  'Initial fixture60106 supplied five functional checks plus three supplementary completion checks; its question expired before phase2. That whole antecedent, including the route-shape timeout and source snapshots, is preserved separately. No old TTL or authority was extended.',
  'Final fixture59142 retained one original native request120s; phase2 snapshot precedes its immutable expiry. No fresh request publication, native decision, Test, Finish, new grant or authority renewal occurred.',
  'The first premature phase2 invocation in final fixture preceded its explicit add-parallel marker and timed out without checks or writes; preserved in phase2-before-marker-cli.txt. Later phase2 begins after the acknowledged distinct fixture fact.',
  'The handoff is a separate public retained synthetic handoff, claimed byB with verify_byoperator. Real Attention returned action_required/verify_handoff and UI opened the exact target/filtered handoffGET200. Operator permissions and native recipient were not changed; no verification decision was sent.',
  'An unlinked request with harness_refs=[] is legitimate and rendered without being invented as a harness. Results is an independent canonical delivery signal with a proven registered-harness reference, not another harness card.',
  'Both fixture connections lack display names/host labels; the UI honestly says Unnamed collaborator/Host not reported. Identity/provenance assertions use exact canonical IDs, not visual label uniqueness. No human usability clarity is inferred.',
  'Technical scope includes current-target Review, read-only activity inspection, unlinked cursor pagination, desktop/360 geometry and selected-project Add GET-only. No decision application, actual reconnection, real-host/provider execution, screen-reader/AT or first-project browser flow is qualified.',
  'Screenshots represent their exact phase snapshot; all mobile categories are captured separately, not claimed to fit in one viewport.'],
 'screenshots':{'blocked':'final/phase1-desktop.png','working':'final/phase2-desktop.png','mobile':['final/phase2-mobile-active.png','final/phase2-mobile-needs_you.png','final/phase2-mobile-results.png'],'add':'final/add-get-only.png'},
 'cleanup':{'browser_session':'r3-harness-board','browser_daemon_pid':41712,'owned_chrome_pid':59668,'fixture_pid':52600,'fixture_exec_session':6201,'browser_close_exit_code':0,'fixture_exit_code':0,'physical_check_at':'2026-11-17T04:19:59.7547336Z','browser_daemon_absent':True,'owned_chrome_absent':True,'fixture_absent':True,'listener59142_absent':True,'peer_wss_factory':json.loads((dest/'cleanup.json').read_text()),'tools':{'owned_chrome_inventory':'715f4f','browser_close':'3b20e1','fixture_exit':'160a53','physical_exit':'01c3db'},'data_preserved':True},
 'provider_calls':0,'native_binary_calls':0,'browser_POST':0,'human_window_opened':False,'product_git_ledger_build_changes_by_agent':False}
(here/'qualification.json').write_text(json.dumps(qualification,ensure_ascii=False,indent=2),encoding='utf-8')
manifest={str(p.relative_to(here)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in here.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__'not in p.parts}
(here/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'qualification_sha256':manifest['qualification.json'],'manifest_entries':len(manifest),'functional_pass':14,'source_drift':drift,'prior_drift':prior_drift,'native_expiry':native[0]['expires_at'],'phase2_generated_at':second['board']['generated_at'],'facts':facts}))
