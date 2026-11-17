from pathlib import Path
import hashlib
import json
import shutil
import sqlite3

here=Path(__file__).resolve().parent
base=here.parent
root=base.parents[3]
control=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui043-fourth-control-0e3arciw')
frozen=json.loads((base/'manifest.json').read_text())
drift=[p for p,h in frozen.items() if hashlib.sha256((base/p).read_bytes()).hexdigest()!=h]
assert not drift,drift
for name in ('ready.json','actions.json','peer-status.json','cleanup.json'):
    shutil.copy2(control/name,here/name)
shutil.copy2(root/'output/playwright/ui043-fourth-human/initial-home.png',here/'initial-home-before-handoff.png')
ready=json.loads((here/'ready.json').read_text())
actions=json.loads((here/'actions.json').read_text())
clicks=[a for a in actions if a['type']=='ui_action']
writes=[a for a in actions if a['type']=='http' and a['method']!='GET']
conn=sqlite3.connect((Path(ready['home'])/'home/nexus.db').as_uri()+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
facts={'setup_commits':conn.execute('SELECT count(*) FROM connection_setup_commits').fetchone()[0],
       'bindings':[dict(r) for r in conn.execute('SELECT binding_id,binding_revision FROM execution_bindings')],
       'sessions':[dict(r) for r in conn.execute('SELECT session_id,lifecycle_state FROM execution_sessions')],
       'operation_action_counts':[dict(r) for r in conn.execute('SELECT action,count(*) AS count FROM execution_operations GROUP BY action')],
       'original_grants_preserved':all(dict(conn.execute('SELECT grant_id,expires_at,max_executions FROM runtime_execution_grants WHERE grant_id=?',(g['grant_id'],)).fetchone())==g for g in ready['original_grants'])}
conn.close()
assert len(clicks)==8 and writes==[] and facts['setup_commits']==0 and facts['original_grants_preserved']
feedback='Nao entendi o conceito de abra uma conexao ja registrada no projeto sample project para voltar a acompanha-la. O que seria isso? Do ponto de vista de usuário, eu deveria ver APENAS harnesses registrados com os status active, Needs you, results. DENTRO do card de cada harness deveriam ter os eventos. Nao entendi a variedade de cards em active.'
qualification={'status':'INCOMPLETE_CONCEPT_MISMATCH_NO_PASS','participant':'Same participant with prior exposure and feedback; fourth iterative simulation, not a new blind novice.',
 'feedback_literal':feedback,'feedback_source':'Anonymous literal supplied in parent /root message; exact chat send/response timestamps unavailable.',
 'reason':'Participant corrected the intended organizing concept: registered harness cards with events inside, arranged by Active/Needs you/Results; the existing variety of activity cards did not match that model. Round stopped for concept correction, not treated as successful usability acceptance.',
 'observations':{'trusted_click_count':len(clicks),'trusted_clicks':clicks,'writes':writes,
    'binding_reads':[a for a in actions if '/connections/bindings/' in a.get('path','')],
    'home_target_reads':[a for a in actions if a.get('path')=='/api/v1/home/target'],
    'http_status_counts':{str(s):sum(a.get('status')==s for a in actions if a['type']=='http') for s in sorted({a['status'] for a in actions if a['type']=='http'})}},
 'facts':facts,'preparation_manifest_entries':len(frozen),'preparation_manifest_sha256':hashlib.sha256((base/'manifest.json').read_bytes()).hexdigest(),'preparation_pin_drift':drift,
 'limits':['Eight trusted clicks are observed, not eight completed tasks. Session/context GET200 and Continue button clicks do not establish participant understanding or an executed continuation; no POST occurred.',
    'Initial preparation HTTP reads and initial screenshot precede handoff and are not human actions. No draft/input, personal data, auth header, cookie, credential, response body or query was captured by the observer.',
    'Exact task-send/feedback timestamps and completion duration are unavailable. Do not derive completion time from first/last click.',
    'Base has two distinct canonical bindings/sessions with repeated subject/Codex/unnamed-host display labels. This limitation was disclosed before handoff; no agent/host/authority was invented or changed.',
    'The original120second native request expired before task1 and was retained only as antecedent. No new question, authority renewal, observation extension or provider call was issued. Decision expiry is separate from this concept feedback.',
    'Initial result is correlated to nonterminal work, so Results0 does not establish missing result data. No extra result card was fabricated.',
    'Only initial owned browser screenshot is retained. No screenshot or DOM inspection was taken under the participant after handoff.'],
 'cleanup':{'browser_session':'ui043-fourth-human','browser_cli_close_exit_code':0,'browser_daemon_pid':52712,'fixture_exec_session':56736,'fixture_pid':36324,'fixture_exit_code':0,
   'physical_check_at':'2026-11-17T03:19:44.3826321Z','browser_daemon_absent':True,'fixture_absent':True,'listener49774_absent':True,'peer_wss_factory':json.loads((here/'cleanup.json').read_text()),
   'evidence_tools':{'browser_close':'5f6fcd','fixture_exit':'fc5888','physical_check':'f534b8'},'data_preserved':True,'chrome_children':'Not separately inventoried; named owned browser close0 observed. No claim about unrelated Chrome processes.'},
 'provider_calls':0,'native_binary_calls':0,'new_human_prompt':False,'product_or_ledger_changes':False}
(here/'qualification.json').write_text(json.dumps(qualification,ensure_ascii=False,indent=2),encoding='utf-8')
pins={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in here.iterdir() if p.is_file() and p.name!='manifest.json'}
(here/'manifest.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
print(json.dumps({'qualification_sha256':pins['qualification.json'],'entries':len(pins),'preparation_entries':len(frozen),'preparation_drift':drift,'clicks':len(clicks),'POST':len(writes),'facts':facts}))
