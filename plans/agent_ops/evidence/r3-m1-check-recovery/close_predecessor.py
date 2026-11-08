from pathlib import Path
import json,hashlib,datetime
T=Path('C:/Users/jpamb/AppData/Local/Temp');R=T/'m1-fresh-v8-pg0b6zbf/campaign'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
c=json.loads((R/'private/controller.json').read_text())
result=json.loads((R/'public/local-setup-result.json').read_text())
cleanup=json.loads((R/'public/final-cleanup-verification.json').read_text())
d=T/'m1-v8-check-diagnosis-vvs0j1al/diagnosis.json';diagnosis=json.loads(d.read_text())
assert cleanup['status']=='PASS' and all(cleanup['tasks_absent'].values())
assert c['faults']==['SETUP_CLI_RETURNED_WITHOUT_SETTLED_USAGE']
assert all(n==0 for n in diagnosis['counts'].values()) and diagnosis['profile']['state']=='check_submitted'
closure={'format':'okto.m1.closed_campaign','revision':1,'campaign_revision':8,
 'closed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'status':'CLOSED_AFTER_VERSION_CHECK_RESPONSE_LOSS_NO_M1_ACCEPTANCE',
 'proposal_sha256':c['proposal_sha256'],'controller_checkpoint_sha256':sha(R/'private/controller.json'),
 'faults_preserved':c['faults'],'controller_mutated':False,
 'cumulative_reserved_admissions':3,'new_reserved_admissions':1,
 'historical_confirmed_productive_admissions':2,'new_confirmed_productive_admissions':0,
 'new_observed_tokens':0,'carry_in_minimum_observed_tokens':45843,'billing_final':False,
 'closed_without_force':True,'replay_allowed':False,'all_temporary_tasks_absent':True,
 'data_retained':True,'first_useful_result':False,'acceptance_promoted':False,
 'evidence_sha256':{name:sha(R/'public'/name) for name in ('local-setup-result.json','cleanup-nexus.json','final-cleanup-verification.json','lifecycle-nexus-uninstall-result.json')},
 'diagnosis_sha256':sha(d),
 'limits':'Read-only SQLite projection places the stop before setup:test. The conservative reserved slot and permanent fault remain; zero observed usage is not final billing. A successor needs its own reviewed proposal and approval.'}
p=R/'public/closure.json'
with p.open('x',encoding='utf-8') as f:json.dump(closure,f,indent=2);f.write('\n')
print(json.dumps({'path':str(p),'sha256':sha(p),'controller_checkpoint_sha256':closure['controller_checkpoint_sha256']}))
