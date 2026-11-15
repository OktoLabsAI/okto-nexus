"""Finite offline U4 composition from actual L2 and canonical renewal receipts."""
from pathlib import Path
from copy import deepcopy
import json,sys
H=Path(__file__).parent;sys.path.insert(0,str(H))
from request_context import read_json,pin,sha,reserve,require
from denial_reconciliation import validate_receipt,IDS
U3=H.parent/'sonnet-successor03-offline-hkf9e8i2'
L=H.parent/'sonnet-after-denial05-lifecycle-bpnawv63'
def ref(p):
    p=Path(p);return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
require(not (H/'work-plan.json').exists() and not (H/'paid-work').exists(),'ALREADY_COMPOSED')
old=read_json(U3/'work-plan.json');require(sha(U3/'work-plan.json')=='0f70f46dd7b4a2cefd083ecf6a83dcea896b1c3b612ed5ff99f073c39ef46be3','OLD_PLAN_CHANGED')
p=deepcopy(old);life=read_json(L/'lifecycle-plan.json')
expected={'nexus':(18908,'b20494f572b5601e980c21cfcecdcfc3'),'connector':(7768,'efb2725714442855c6aa25630b1bf70b')}
for component in expected:
    selection=read_json(L/'public'/(component+'-owner-selection.json'))
    watch=read_json(L/'public'/(component+'-exit-watch-started.json'))
    require((selection['pid'],selection['generation'])==expected[component],'CURRENT_OWNER_CHANGED')
    require(selection['cohort']==watch['cohort'] and selection['lifecycle_plan_sha256']==watch['lifecycle_plan_sha256']==sha(L/'lifecycle-plan.json'),'CURRENT_COHORT_CHANGED')
    require(not (L/'public'/(component+'-exit-proof.json')).exists() and not (L/'public'/(component+'-exit-watch-timeout.json')).exists(),'CURRENT_WATCH_TERMINAL')
    for suffix,filename in [('selection','owner-selection'),('watch_started','exit-watch-started')]:
        p['prerequisites'][component+'_'+suffix]=ref(L/'public'/(component+'-'+filename+'.json'))
checkpoint=Path(life['paths']['operator_home'])/'terminal/work'/(p['profile']+'.json')
doc=read_json(checkpoint);auth=doc.get('authorization',{})
require(doc['session_id']=='ses_421253fe45b0d98592fede20d45c12b6' and auth.get('state')=='done','CURRENT_WORK_ANCESTRY_CHANGED')
receipt=auth['result'];grant=receipt['result']['grant']
require(grant['grant_id']=='grant_3fbf5b1b947f46729770b9daf0287eef' and grant['max_executions']==3
    and grant['expires_at']=='2026-11-15T16:24:41.207084Z','RENEWAL_RECEIPT_CHANGED')
require(receipt['state']=='authorization_committed' and receipt['client_request_id']=='authorize_795e604486da4ffe9eea9a9c3ef4d5a0'
    and receipt['request_hash']=='sha256:5e641c6767f2aa499890e8eebdfc7d20c8b2bf1513cd1b675687e70b5b0acd1a','RENEWAL_AUTHORITY_CHANGED')
renewal={'status':'CANONICAL_RENEWAL_CONFIRMED','root_execution_reference':'apply882fe8 exit0 / reviewe5106e',
    'source':'Existing canonical checkpoint authorization.result, projected without credentials',
    'checkpoint_pin':ref(checkpoint),'grant_id':grant['grant_id'],'expires_at':grant['expires_at'],
    'max_executions':3,'actions':grant['actions'],'scope':receipt['result']['scope'],
    'client_request_id':receipt['client_request_id'],'request_hash':receipt['request_hash'],
    'runtime_revalidation':'Canonical read-only authorizations:review before each new work reservation; no issuance or checkpoint write.'}
reserve(H/'canonical-renewal-projection.json',renewal)
p['prerequisites']['canonical_renewal']=ref(H/'canonical-renewal-projection.json')
p['recovery_plan']=p['restart_plan']=ref(L/'lifecycle-plan.json')
p['restart_context_source']=ref(L/'recovery_context.py')
p['predecessor_work_checkpoint']=ref(checkpoint);p['predecessor_session_id']=doc['session_id']
p['predecessor_exit_proofs']=life['old_exits'];p['predecessor_paid_plan']=ref(U3/'work-plan.json')
p['project']=life['campaign_root'];p['remote_workspace_root']=life['paths']['connector_project']
p['request_ids']=IDS;p['prompts']=read_json(H/'task-prompts.json')
p['successor_candidate']=ref(H/'candidate.json');p['budget_authorization']=ref(H/'authorization-record.json')
p['budget_seed']=ref(H/'budget-seed-approved.json')
p['successor']={'namespace':str(H/'paid-work'),'new_requests':2,'global_max_requests':4,
 'global_max_server_attempts':5,'historical_observed_tokens':144004,'historical_charged_requests':2,
 'historical_server_admissions':3,'old_useful05_consumed_no_replay':True,'old_conditional06_ineligible':True,
 'no_refund':True,'force_selected':False}
for key,filename in [('counter_selection','root-counter-selection.json'),('typed_denial05','typed-denial05.json'),('server_admission_history','server-admission-history.json')]:p[key]=ref(H/filename)
validate_receipt(p)
p['accounting']='144004 tokens, 2 historical Native charges, 3 consumed Server admissions. Only exact typed05 is positively pre-Core/zero native.07/08 always consume Native-or-uncertain slots; Native maximum4, Server maximum5. No old reservation refunded.500k/480k and conservative reserve formula unchanged.'
oldfreeze=read_json(pin(old['work_runtime_freeze']))
names=('sonnet_usage.py','remote_work.py','observe_active.py','activecontrol.py','request_context.py','reused_observation.py','successor_policy.py','denial_reconciliation.py','grant_preflight.py')
reserve(H/'work-runtime-freeze.json',{'files':{n:ref(H/n) for n in names},'dependencies':oldfreeze['dependencies'],'original_freeze':old['work_runtime_freeze']})
p['work_runtime_freeze']=ref(H/'work-runtime-freeze.json')
p['runtime_pins']={n:ref(H/n) for n in ('work_context.py','work-entry.py','successor_policy.py','denial_reconciliation.py','grant_preflight.py')}
for item in p['prerequisites'].values():pin(item)
reserve(H/'work-plan.json',p)
commands={action:[life['python'],'-I','-B','-X','utf8',str(H/'work-entry.py'),'--plan',str(H/'work-plan.json'),'--expected-plan-sha256',sha(H/'work-plan.json'),action] for action in ('prepare','useful','continuation')}
reserve(H/'commands.json',{'commands':commands,'paid_execution_selected_by_this_script':False,'continuation_conditional_on_useful_success_and_rechecked_budget':True})
print(json.dumps({'plan':ref(H/'work-plan.json'),'commands':ref(H/'commands.json'),'renewal_projection':ref(H/'canonical-renewal-projection.json'),'provider_calls':0,'service_effects':0}))
