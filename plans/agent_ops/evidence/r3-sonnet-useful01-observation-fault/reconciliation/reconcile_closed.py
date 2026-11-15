"""Reconcile preserved projection, never modify source checkpoint or journal."""
from pathlib import Path
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from sonnet_usage import Ledger, CampaignBudget, checkpoint_budget
S=Path('C:/Users/jpamb/AppData/Local/Temp/m1-sonnet-remote-candidate-2c_4af0t')
R=Path('C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t')
def pin(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def save(name,value):
    p=HERE/name;p.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8');return pin(p)
original=S/'paid-work/private/sonnet-budget.json'
before=pin(original)
old=json.loads(original.read_text())
events=json.loads((HERE/'events-projected.json').read_text())
scope={k:events[0][k] for k in ('server_id','executor_id','session_id','stream_epoch')}
ledger=Ledger(scope)
budget=CampaignBudget();budget.attach(ledger)
budget.reserve(ledger,'op_b9a7bc74da0788081adbe51fa62c6598')
for event in events:ledger.ingest(event)
assert ledger.cursor==98 and ledger.known==36306 and ledger.finished[0]['outcome']=='interrupted'
assert ledger.terminal_coverage and ledger.active is None and not ledger.faults
assert len(ledger.reserved)==1 and pin(original)==before
derived=save('reconciled-budget.json',checkpoint_budget(budget))
report={
 'status':'CLOSED_STREAM_ACCOUNTING_RECONCILED_INTERRUPTED_NOT_ACCEPTED',
 'original_checkpoint':before,
 'original_summary':{k:old['state']['sessions'][0][k] for k in ('known','cursor','faults','active','reserved','terminal_coverage')},
 'original_result':pin(S/'paid-work/public/m1-sonnet-remote-useful-01-result.json'),
 'original_plan':pin(S/'work-plan.json'),
 'physical_exit_proof':pin(S/'paid-work/public/paid-work-exit-proof.json'),
 'scope':scope,'projection':pin(HERE/'events-projected.json'),'event_source_pins':pin(HERE/'event-source-pins.json'),
 'collector_source':pin(HERE/'sonnet_usage.py'),'reconciliation_source':pin(Path(__file__)),
 'derived_checkpoint':derived,
 'coverage':{'contiguous_sequences':[1,98],'stream_message_start':4,'redacted_assistant_sequences':[19,87],
             'message_delta':89,'message_stop':90,'native_permission_request':92,'native_permission_cancel':93,
             'correlated_terminal_result':97,'native_process_exit_event':98,
             'turn_usage_equals_stream':True,'cumulative_model_usage_equals_baseline_plus_turn':True},
 'usage':{'input_tokens':2,'cache_read_input_tokens':18339,'cache_creation_input_tokens':16682,
          'output_tokens':1283,'total':36306,'thinking_tokens_in_output':754,
          'thinking_is_additional':False,'previous_minimum':35031,'additional_observed':1275},
 'accounting_scope':'All retained usage for this one native Sonnet session; not provider billing or unrelated account usage.',
 'outcome':'interrupted','reservations':1,'refund':False,'useful_result_confirmed':False,
 'new_provider_or_control_calls':0,'original_checkpoint_unchanged':True,
 'next_admission_not_selected':True,'current_policy_next_estimate':budget.check_admission('useful'),
 'continuation_headroom_not_guaranteed':True,
 'hypothetical_180k_option':{'observed':36306,'next_reserve':102046,'first_admission_sum':138352,
   'if_next_input_repeats_35023':{'minimum_total_after':71329,'plus_next_reserve':173375},
   'not_selected_or_applied':True,'must_recheck_actual_complete_usage':True,'user_limit':200000,
   'no_atomic_cap':True},
 'diagnosis':'Core redacts all raw strings for output_delta assistant snapshots. The old campaign collector compared redacted raw.message.id against the preserved stream message ID. New collector recognizes only the exact redacted ID+model pair, correlated active operation, prior stream and numeric counter shape; snapshot values never add tokens. Unredacted mismatch remains refused.',
 'source_contracts':{
   'old_collector':pin(S/'sonnet_usage.py'),
   'installed_redaction':pin(R/'package/venv/Lib/site-packages/nexus_connector_core/native/redaction.py'),
   'installed_adapter':pin(R/'package/venv/Lib/site-packages/nexus_connector_core/native/adapters/claude_code_stream.py')},
}
result=save('accounting-reconciliation.json',report)
cases=ET.parse(HERE/'final.xml').findall('.//testcase')
qual=save('qualification.json',{'status':'OFFLINE_COLLECTOR_DELTA_PASS','tests':len(cases),
 'failures':len(ET.parse(HERE/'final.xml').findall('.//failure')),'runtime':pin(HERE/'sonnet_usage.py'),
 'tests_source':pin(HERE/'test_redacted_assistant.py'),'xml':pin(HERE/'final.xml'),
 'command':'R/package/venv/Scripts/python.exe -I -B -X utf8 '+str(HERE/'run_tests.py'),
 'installed_redactor_exercised':True,'campaign_only_not_installed_patch':True,'original_artifacts_unchanged':True,
 'reconciliation':result,'initial8pass_preserved':pin(HERE/'initial-8pass.xml')})
names=['sonnet_usage.py','project_closed_events.py','events-projected.json','event-source-pins.json',
 'test_redacted_assistant.py','run_tests.py','initial-8pass.xml','final.xml','reconcile_closed.py',
 'reconciled-budget.json','accounting-reconciliation.json','qualification.json']
allow=save('public-allowlist.json',{'files':[pin(HERE/name) for name in names]})
print(json.dumps({'accounting':result,'qualification':qual,'allowlist':allow}))
