from pathlib import Path
import hashlib
import json
import shutil
import sqlite3

here = Path(__file__).resolve().parent
root = here.parents[3]
out = root / 'output/playwright/ui-board-final'
control = Path(json.loads((out/'control.json').read_text())['control'])
dest = here/'final'
dest.mkdir(exist_ok=True)
for name in ('ready.json','cleanup.json','actions.json','peer-status.json'):
    shutil.copy2(control/name,dest/name)
for name in ('browser.js','result.json','runtime-pins.json','preflight-board.json'):
    shutil.copy2(out/name,dest/name)
for path in out.glob('*.png'):
    # Preserve failed/scroll-bottom screenshots in their explicit antecedent,
    # rather than presenting them as the final visual qualification.
    if path.name=='failure.png' or path.name=='desktop-board.png':
        continue
    shutil.copy2(path,dest/path.name)
result=json.loads((dest/'result.json').read_text())
capture_raw=(here/'capture-cli.txt').read_text(encoding='utf-8-sig')
capture=json.loads(capture_raw.split('### Result\n',1)[1].split('\n### Ran',1)[0])
pins=json.loads((dest/'runtime-pins.json').read_text())
drift=[p for p,digest in pins.items() if hashlib.sha256((root/p).read_bytes()).hexdigest()!=digest]
assert not drift, drift
prior=here.parent/'pr15-human-third-prepare'
prior_pins=json.loads((here/'pr15-manifest-copy.json').read_text())
prior_drift=[p for p,digest in prior_pins.items() if hashlib.sha256((prior/p).read_bytes()).hexdigest()!=digest]
assert not prior_drift,prior_drift
ready=json.loads((dest/'ready.json').read_text())
conn=sqlite3.connect((Path(ready['home'])/'home/nexus.db').as_uri()+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
finished=next(e['data'] for e in result['envelopes'] if e['phase']=='normal canonical Finish')
facts={'setup_commits':conn.execute('SELECT count(*) FROM connection_setup_commits').fetchone()[0],
       'saved_binding':dict(conn.execute('SELECT b.binding_id,b.binding_revision,w.workspace_id,e.agent_id FROM execution_bindings b JOIN execution_workspace_bindings w ON w.server_id=b.server_id AND w.executor_id=b.executor_id AND w.workspace_binding_id=b.workspace_binding_id JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id WHERE b.binding_id=?',(finished['binding']['binding_id'],)).fetchone()),
       'new_collaborator_operations':conn.execute('SELECT count(*) FROM execution_operations WHERE actor_agent_id=?',(finished['agent_id'],)).fetchone()[0],
       'original_grants_preserved':all(dict(conn.execute('SELECT grant_id,expires_at,max_executions FROM runtime_execution_grants WHERE grant_id=?',(g['grant_id'],)).fetchone())==g for g in ready['original_grants'])}
conn.close()
counts={status:sum(c['status']==status for c in result['checks']) for status in ('PASS','FAIL','NOT_RUN')}
assert result['status']=='PASS' and counts=={'PASS':24,'FAIL':0,'NOT_RUN':1},counts
assert len([r for r in result['requests'] if r['method']=='POST'])==3
assert result['pageErrors']==[] and capture['status']=='PASS'
qualification={'status':'PASS_FOCUSED_WITH_ONE_NOT_RUN_NO_HUMAN_APPROVAL','checks':result['checks'],'check_counts':counts,
 'source_pins':pins,'source_pin_drift':drift,'prior_pr15_pin_drift':prior_drift,
 'root_build_reference':'NEXUS_UI_R1/execution/pr19-board-frontend/qualification.json; root reported328/328Node PASS and TSC/Vite PASS.',
 'facts':facts,'requests':result['requests'],'responses':result['responses'],'envelopes':result['envelopes'],
 'pageErrors':result['pageErrors'],'consoleErrors':result['consoleErrors'],
 'console_limit':'Exactly one net::ERR_FAILED from explicitly lost canonical inert Test response after actual handler200; no other console error and no page exception.',
 'supplementary_capture':capture,
 'screenshots':{'desktop_board':'desktop-board-clear.png','mobile_columns':['mobile-active-clear.png','mobile-needs_you-clear.png','mobile-results-clear.png'],'confirmed':'desktop-connected.png','mobile_confirmed':'mobile-connected.png','pending':['pending-test.png','pending-finish.png'],'unknown':'unknown.png'},
 'scope':'Canonical HTTP/SQLite projection and real own Chromium UI only; inert Test peer; synthetic retained facts, not real provider execution or human usability approval.',
 'limits':['Needs you had one real item and no has_more; its browser cursor pagination is NOT_RUN. Active and Results pagination were exercised independently to completion.',
 'Synthetic VERIFYING handoffs and later copied OUTCOME_UNKNOWN pairs did not create additional action-required board entries for this canonical loopback operator. No permission or DTO was changed to force them into Needs you.',
 'Fixture retained history/results are synthetic canonical relation facts and do not establish native execution success. The two normal POSTs are actual inert Test and validated canonical Finish; a distinct third Test has a deliberately lost response and stays UNKNOWN without replay.',
 'The1.5second fixture delay holds delivery of actual Test/Finish HTTP responses without rewriting DTOs; it demonstrates real pending UI, not provider latency or fake percentage progress.',
 'Supplementary clear board screenshots were captured after Finish added a connection (Active31 versus initial30). Their counts correspond to that later snapshot; initial assertions remain in the raw result envelope.',
 'Default classic-Home preference was explicitly switched to operational in the own technical profile, matching prior PR15 fixture setup. This focused qualification does not establish the default experience of a fresh user profile.',
 'An initial seed-column error, a classic-preference timeout and a broad heading locator error are preserved as harness antecedents. All occurred before any Test/Finish POST. No uncertain mutation was repeated.',
 'No human window opened and no human understanding or scenario acceptance inferred from these automated checks. No screen-reader/native zoom claim.'],
 'cleanup':{'browser_session':'ui-board-final','browser_daemon_pid':18784,'browser_cli_close_exit_code':0,'fixture_pid':12964,'fixture_exec_session':36469,'fixture_exit_code':0,'physical_check_at':'2026-11-17T02:22:34.8378565Z','browser_daemon_absent':True,'fixture_absent':True,'listener56034_absent':True,'peer_wss_factory':json.loads((dest/'cleanup.json').read_text()),'chrome_child_pid_inventory':'Not separately captured; named browser close0 observed. No claim about other Chrome processes.','data_preserved':True},
 'provider_calls':0,'native_binary_calls':0}
(here/'qualification.json').write_text(json.dumps(qualification,ensure_ascii=False,indent=2),encoding='utf-8')
manifest={str(p.relative_to(here)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in here.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
(here/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'qualification_sha256':manifest['qualification.json'],'manifest_entries':len(manifest),'check_counts':counts,'source_drift':drift,'prior_drift':prior_drift,'facts':facts}))
