from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
R=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checkpoint=R/'private/controller.json';before=sha(checkpoint)
c=json.loads(checkpoint.read_text());s=json.loads((R/'public/local-setup-result.json').read_text())
f=json.loads((R/'public/final-presence.json').read_text())
error=json.loads((R/'public/m1v10-local-work-01-runner-error.json').read_text())
assert set(c['requests'])=={'m1v10-local-setup'} and c['faults']==['CAMPAIGN_RUNNER_EXCEPTION']
assert s['monitor']['result_stage']=='SUCCEEDED' and s['monitor']['owned_slot_released']
assert f['status']=='NORMAL_CLEANUP_CONFIRMED' and f['work_intent_rows']==0
assert error['request'] is None and error['error_type']=='OperationalError'
diagnosis={'error_type':'sqlite3.OperationalError','observed_message':'interrupted',
    'source':'own execution stderr, sanitized frame/function/message projection',
    'frames':[{'file':'m1_v10_work.py','line':195,'function':'module'},
              {'file':'independent_controller.py','line':102,'function':'start_work'},
              {'file':'independent_journal.py','line':78,'function':'read'}],
    'failed_before_work_reservation':True,'failed_before_work_api_dispatch':True,
    'work_intent_rows':0,'work_model_turns':0,
    'original_numeric_sqlite_code_retained':False,
    'scope':'Freshness SELECT failed in the campaign observer. This is not the v9 product DB_ERROR and not a provider failure.'}
with (R/'public/observer-error-diagnosis.json').open('x',encoding='utf-8') as stream:json.dump(diagnosis,stream,indent=2)
names=['local-setup-result.json','m1v10-local-work-01-runner-error.json','cleanup-nexus.json',
       'final-presence.json','lifecycle-nexus-uninstall-result.json','observer-error-diagnosis.json']
closure={'format':'okto.m1.closed_campaign','revision':1,'campaign_revision':10,
    'closed_at':datetime.now(timezone.utc).isoformat(),
    'status':'CLOSED_AFTER_OBSERVER_PREFLIGHT_FAILURE_NO_M1_ACCEPTANCE',
    'proposal_sha256':'90c2ed2ca18e7fd86380c614e516a5f8975af2a2052b56a3609004be4814405a',
    'approval_sha256':'8500ae2cd11ff8dca2bc1551a9a5349f76075a0578f2e931c436a09ee2515620',
    'controller_checkpoint_sha256':before,'faults_preserved':c['faults'],'controller_mutated':False,
    'cumulative_reserved_admissions':6,'new_reserved_admissions':1,
    'historical_confirmed_productive_admissions':3,'new_confirmed_productive_admissions':1,
    'productive_confirmation_scope':'Local connection test only. Useful work failed before reservation and any POST/native admission.',
    'new_observed_tokens':21815,'carry_in_minimum_observed_tokens':89473,'prior_carry_in_tokens':67658,
    'billing_final':False,'closed_without_force':True,'replay_allowed':False,
    'all_temporary_tasks_absent':True,'data_retained':True,'first_useful_result':False,
    'acceptance_promoted':False,'service_actions':4,'connector_started':False,
    'optional_claude_executed':False,'evidence_sha256':{name:sha(R/'public'/name) for name in names},
    'limits':'No work admission or report. Observer failure and all previous faults remain unchanged. Observed usage is not final billing. No campaign replay is authorized by this closure.'}
assert sha(checkpoint)==before
with (R/'public/closure.json').open('x',encoding='utf-8') as stream:json.dump(closure,stream,indent=2)
print(json.dumps({'closure_sha256':sha(R/'public/closure.json'),'checkpoint_sha256':before,'status':closure['status'],'minimum_observed_tokens':89473,'cumulative_reservations':6}))
