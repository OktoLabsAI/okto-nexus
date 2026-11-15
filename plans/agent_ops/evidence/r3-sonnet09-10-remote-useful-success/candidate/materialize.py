"""Future one-time offline composition, only after explicit answer and fresh facts."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys
H=Path(__file__).parent;sys.path.insert(0,str(H))
from request_context import require,read_json,pin,sha,reserve
from successor_policy import authorize,convert,IDS
def ref(p):
 p=Path(p);return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
def materialize(authorization):
    require(Path(authorization).is_file(),'AUTHORIZATION_PENDING')
    candidate=read_json(H/'candidate.json');record=read_json(authorization);authorize(record,candidate)
    require(not (H/'work-plan.json').exists() and not (H/'paid-work').exists(),'ALREADY_MATERIALIZED')
    p=read_json(pin(candidate['previous_plan']));life=read_json(pin(candidate['lifecycle_plan']));L=Path(candidate['lifecycle_plan']['path']).parent
    for component in ('nexus','connector'):
        selected=read_json(L/'public'/(component+'-owner-selection.json'));watch=read_json(L/'public'/(component+'-exit-watch-started.json'))
        previous=read_json(pin(life['old_selections'][component]))
        require(selected['cohort']==watch['cohort'] and selected['generation']!=previous['generation']
            and selected['cohort']['cycle_id']!=previous['cohort']['cycle_id'],'FRESH_COHORT_REQUIRED')
        require(selected['lifecycle_plan_sha256']==watch['lifecycle_plan_sha256']==candidate['lifecycle_plan']['sha256'],'CURRENT_LIFECYCLE_CHANGED')
        require(not (L/'public'/(component+'-exit-proof.json')).exists() and not (L/'public'/(component+'-exit-watch-timeout.json')).exists(),'CURRENT_OBSERVER_TERMINAL')
        for suffix,filename in [('selection','owner-selection'),('watch_started','exit-watch-started')]:p['prerequisites'][component+'_'+suffix]=ref(L/'public'/(component+'-'+filename+'.json'))
    checkpoint=Path(life['paths']['operator_home'])/'terminal/work'/(p['profile']+'.json')
    document=read_json(checkpoint);auth=document.get('authorization',{})
    require(document['session_id']=='ses_6cc8d4a0113d28342d31cf843de63ac5' and auth.get('state')=='done','CURRENT_CHECKPOINT_REQUIRED')
    receipt=auth['result'];grant=receipt['result']['grant']
    require(receipt['state']=='authorization_committed' and grant['max_executions']==3
        and grant['grant_id']!='grant_3fbf5b1b947f46729770b9daf0287eef'
        and set(grant['actions'])=={'open','send','steer','interrupt','close'}
        and (datetime.fromisoformat(grant['expires_at'].replace('Z','+00:00'))-datetime.now(timezone.utc)).total_seconds()>=600,'CURRENT_GRANT_WINDOW_REQUIRED')
    p['selected_grant_id']=grant['grant_id']
    p['recovery_plan']=p['restart_plan']=candidate['lifecycle_plan'];p['restart_context_source']=ref(L/'recovery_context.py')
    p['predecessor_work_checkpoint']=ref(checkpoint);p['predecessor_session_id']=document['session_id']
    p['predecessor_exit_proofs']=life['old_exits'];p['predecessor_paid_plan']=candidate['previous_plan']
    p['project']=life['campaign_root'];p['remote_workspace_root']=life['paths']['connector_project']
    p['request_ids']=IDS;p['successor_candidate']=ref(H/'candidate.json');p['budget_authorization']=ref(authorization)
    p['phase_reserve_policy']=read_json(pin(candidate['proposal']))['proposed']['reserve_policy']
    p['successor']={'namespace':str(H/'paid-work'),'new_requests':2,'global_max_requests':5,'global_max_server_attempts':6,
        'historical_observed_tokens':180426,'historical_charged_requests':3,'historical_server_admissions':4,
        'old07_consumed_no_replay':True,'old08_ineligible':True,'no_refund':True,'force_selected':False}
    p['server_admission_history']=candidate['current_server_history']
    p['predecessor_counter_selection']=p.pop('counter_selection')
    p['svc09_console_selected']=False
    p['accounting']='Explicitly approved Native5/Server6; preserve180426/Native3/Server4. Only textual continuation reserve uses1x; useful2x unchanged. No automatic new Native exception.'
    p['prompts']=read_json(H/'task-prompts.json')
    p.pop('transport_correction',None)
    seed=convert(read_json(pin(candidate['current_seed'])),record,candidate)
    reserve(H/'budget-seed-approved.json',seed);p['budget_seed']=ref(H/'budget-seed-approved.json')
    oldfreeze=read_json(pin(p['work_runtime_freeze']))
    names=['sonnet_usage.py','remote_work.py','observe_active.py','activecontrol.py','request_context.py','reused_observation.py',
        'successor_policy.py','denial_reconciliation.py','successor_allocation.py','grant_preflight.py','context_hooks.py','fast_approval.py']
    reserve(H/'work-runtime-freeze.json',{'files':{n:ref(H/n) for n in names},'dependencies':oldfreeze['dependencies'],'original_freeze':p['work_runtime_freeze']})
    p['work_runtime_freeze']=ref(H/'work-runtime-freeze.json');p['runtime_pins']={n:ref(H/n) for n in ('work_context.py','work-entry.py','successor_policy.py','successor_allocation.py','grant_preflight.py')}
    renewal={'status':'CANONICAL_CHECKPOINT_RENEWAL_OBSERVED','grant_id':grant['grant_id'],'expires_at':grant['expires_at'],
        'max_executions':grant['max_executions'],'scope':receipt['result']['scope'],'checkpoint_pin':ref(checkpoint),
        'runtime_fresh_review_required':True}
    reserve(H/'canonical-renewal-projection.json',renewal);p['prerequisites']['canonical_renewal']=ref(H/'canonical-renewal-projection.json')
    from successor_allocation import validate_receipt
    validate_receipt(p)
    reserve(H/'work-plan.json',p)
    commands={action:[life['python'],'-I','-B','-X','utf8',str(H/'work-entry.py'),'--plan',str(H/'work-plan.json'),'--expected-plan-sha256',sha(H/'work-plan.json'),action] for action in ('prepare','useful','continuation')}
    reserve(H/'commands.json',{'commands':commands,'paid_execution_selected':False,'continuation_conditional':True})
    return {'plan':ref(H/'work-plan.json'),'commands':ref(H/'commands.json'),'provider_calls':0}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--authorization-record',required=True);a=parser.parse_args()
    print(json.dumps(materialize(a.authorization_record)))
