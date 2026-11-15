"""Offline finite successor: exact retained carry, new IDs and fresh cohort receipts."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent
RECOVERY=Path('C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t')
FIX=Path('C:/Users/jpamb/AppData/Local/Temp/r3-sonnet-redacted-assistant-qmtaz0sg')
sys.path.insert(0,str(HERE))
from request_context import read_json,require,sha
from sonnet_usage import restore_budget,checkpoint_budget,digest
from work_context import WORK_IDS


def reference(path):
    path=Path(path);return {'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}


def convert_seed(document):
    # Legacy checkpoint hashed integer sequence keys before JSON changed them to strings.
    # Prove that exact old seal first; never accept an arbitrary changed checkpoint.
    legacy=deepcopy(document)
    for ledger in legacy['state']['sessions']:
        seen=ledger['seen']
        require(all(type(k) is str and k.isascii() and k.isdigit() and int(k)>0
                    and str(int(k))==k for k in seen),'LEGACY_SEQUENCE_KEY_INVALID')
        ledger['seen']={int(k):v for k,v in seen.items()}
    require(digest(legacy['state'])==document['sha256'],'LEGACY_CHECKPOINT_SEAL_CHANGED')
    budget=restore_budget(legacy)
    require(budget.known==36306 and sum(len(row.reserved) for row in budget.sessions.values())==1,
            'EXACT_CARRY_REQUIRED')
    require(budget.preventive==150000,'ORIGINAL_RECONCILIATION_POLICY_CHANGED')
    before=deepcopy(checkpoint_budget(budget)['state'])
    budget.preventive=180000
    for ledger in budget.sessions.values():ledger.preventive=180000
    converted=checkpoint_budget(budget)
    compared=deepcopy(converted['state']);compared['preventive']=150000
    for ledger in compared['sessions']:ledger['preventive']=150000
    require(compared==before,'POLICY_CONVERSION_CHANGED_USAGE')
    return converted


def write_once(name,value):
    with (HERE/name).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')


def main():
    require(not (HERE/'work-plan.json').exists(),'SUCCESSOR_PLAN_ALREADY_EXISTS')
    require(sha(FIX/'sonnet_usage.py')==
        '9fae04d3f7baef6c4e3fbbc2cb2cf77972de584f8cb8be0a2488577ed1af5da8','CORRECTED_COLLECTOR_CHANGED')
    require(sha(FIX/'reconciled-budget.json')=='bd23de47f3ebc96086ca8662abfa0fb24d3ff60677eb5856b51f2e580517cec2',
            'RECONCILED_CARRY_CHANGED')
    require(sha(FIX/'accounting-reconciliation.json')=='c94704923503f738937952693d610c65ba00bbdd1c712677a8fbb6a1bece6ab7',
            'RECONCILIATION_CHANGED')
    converted=convert_seed(read_json(FIX/'reconciled-budget.json'))
    write_once('budget-seed-180k.json',converted)
    write_once('budget-policy-change.json',{'source':reference(FIX/'reconciled-budget.json'),
        'reconciliation':reference(FIX/'accounting-reconciliation.json'),
        'derived':reference(HERE/'budget-seed-180k.json'),'change':'Verify legacy integer-sequence seal, normalize seen keys to JSON strings; then preventive150000 to180000 for global and ledger policies.',
        'known_tokens':36306,'charged_reservations':1,'historical_outcome':'interrupted',
        'user_limit_unchanged':200000,'global_max_requests_unchanged':3,'no_refund':True,
        'root_selected_policy':True,'usage_fields_unchanged':True,
        'legacy_roundtrip_failure_preserved':'a6a41d: 5 setup errors CHECKPOINT_CHANGED before any test body/effect',
        'legacy_seal_verified_before_normalization':True})
    old=read_json(PRIOR/'work-plan.json');plan=deepcopy(old)
    plan['request_ids']=WORK_IDS
    plan['budget']['preventive']=180000
    for key in ('post_svc20_plan','post_svc20_freeze','post_svc20_context_source'):plan.pop(key,None)
    lifecycle=RECOVERY/'post-sonnet-collector-recovery'
    require(sha(lifecycle/'plan.json')=='101ca1a6aad80e849911e2612083ec7575120577f57b41ced7cc16497756a646',
            'RESTART_PLAN_CHANGED')
    plan['restart_plan']=reference(lifecycle/'plan.json')
    plan['restart_context_source']=reference(lifecycle/'lifecycle.py')
    for component in ('nexus','connector'):
        for key,filename in (('selection','owner-selection'),('watch_started','exit-watch-started')):
            path=lifecycle/'public'/(component+'-'+filename+'.json')
            value=read_json(path)
            require(value.get('collector_recovery_plan_sha256')==plan['restart_plan']['sha256'],
                    'CURRENT_COHORT_NAMESPACE_REQUIRED')
            plan['prerequisites'][component+'_'+key]=reference(path)
    phase=read_json(RECOVERY/'lifecycle-plan.json')
    checkpoint=Path(phase['paths']['operator_home'])/'terminal/work'/(plan['profile']+'.json')
    require(sha(checkpoint)=='efd70f3eef84be734e8e33323b571b87f949f2676bd7990683b6d83a2e6009f9',
            'SELECTED_PREDECESSOR_CHECKPOINT_CHANGED')
    document=read_json(checkpoint)
    require(document.get('session_id')=='ses_e13d6e02f5ea6270004c5bf15e298e73'
        and document.get('work',{}).get('state')=='admitted','PREDECESSOR_CHECKPOINT_UNCONFIRMED')
    plan['predecessor_work_checkpoint']=reference(checkpoint)
    plan['predecessor_session_id']=document['session_id']
    plan['predecessor_paid_plan']=reference(PRIOR/'work-plan.json')
    plan['predecessor_six_exit_proof']=reference(PRIOR/'paid-work/public/paid-work-exit-proof.json')
    plan['budget_seed']=reference(HERE/'budget-seed-180k.json')
    plan['budget_policy_change']=reference(HERE/'budget-policy-change.json')
    plan['reconciliation']=reference(FIX/'accounting-reconciliation.json')
    previous_freeze=read_json(PRIOR/'work-runtime-freeze.json')
    files={name:reference(HERE/name) for name in ('sonnet_usage.py','remote_work.py','observe_active.py','activecontrol.py',
        'request_context.py','reused_observation.py')}
    write_once('work-runtime-freeze.json',{'files':files,'dependencies':previous_freeze['dependencies'],
        'original_freeze':reference(PRIOR/'work-runtime-freeze.json'),
        'corrected_collector_qualification':reference(FIX/'qualification.json')})
    plan['work_runtime_freeze']=reference(HERE/'work-runtime-freeze.json')
    plan['runtime_pins']={name:reference(HERE/name) for name in ('work_context.py','work-entry.py')}
    plan['accounting']='Mandatory reconciled carry36306/one charged interrupted admission; global max3. Preventive180000, userlimit200000; each next reserve max(50000,2*previous observed input including cache+32000). No reset/refund; continuation only after actual headroom recheck.'
    plan['successor']={'namespace':str(HERE/'paid-work'),'new_requests':2,'global_max_requests':3,
        'historical_observed_tokens':36306,'historical_charged_requests':1,
        'old_useful01_interrupted_preserved':True,'old_continuation02_not_selected':True,
        'new_session':'Installed CLI --new-session with original checkpoint retained and exact old-session scope guard',
        'no_setup_replay':True,'force_selected':False}
    require(not Path(plan['report']).exists(),'ORIGINAL_REPORT_PATH_ALREADY_EXISTS')
    write_once('work-plan.json',plan)
    print(json.dumps(reference(HERE/'work-plan.json')))


if __name__=='__main__':main()
