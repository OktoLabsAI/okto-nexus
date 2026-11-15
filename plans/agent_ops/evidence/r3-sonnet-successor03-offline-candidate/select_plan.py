"""Future offline composition after actual answer and reviewed fresh installation/cohorts.

Does not start services, construct a live Context or call the provider. Existing
plans/checkpoints are only read. No selected plan is emitted while authorization
or composition is missing.
"""
from pathlib import Path
import argparse,json,sys
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from request_context import require,read_json,pin,sha,reserve
from successor_policy import authorize,convert,IDS,HERE

def ref(path):
    path=Path(path);return {'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--authorization-record',required=True,type=Path)
    p.add_argument('--reviewed-composition',required=True,type=Path)
    p.add_argument('--expected-composition-sha256',required=True)
    a=p.parse_args()
    candidate=read_json(HERE/'candidate.json');pin(candidate['proposal']);pin(candidate['history'])
    authority=read_json(a.authorization_record);authorize(authority,candidate)
    require(sha(a.reviewed_composition)==a.expected_composition_sha256,'COMPOSITION_CHANGED')
    composition=read_json(a.reviewed_composition)
    require(composition['status']=='ROOT_REVIEWED_FRESH_PACKAGE_AND_COHORTS'
            and composition['provider_calls']==0,'FRESH_COMPOSITION_PENDING')
    # Reuse the reviewed canonical context contracts. Fresh binding is supplied
    # by the lifecycle owner after physical cleanup, package upgrade and start.
    plan=deepcopy(read_json(pin(candidate['original_plan'])))
    allowed={'recovery_plan','binding_plan','restart_plan','restart_context_source','prerequisites',
             'predecessor_work_checkpoint','predecessor_session_id','predecessor_six_exit_proof',
             'python_executable','rtk','console_helper'}
    require(set(composition['bindings'])==allowed,'FINITE_BINDINGS_REQUIRED')
    require(composition['bindings']['restart_plan']!=plan['restart_plan'],'EXPIRED_COHORTS_FORBIDDEN')
    for key,value in composition['bindings'].items():plan[key]=value
    for key in allowed-{'predecessor_session_id','prerequisites'}:pin(plan[key])
    for source in plan['prerequisites'].values():pin(source)
    require(composition['bindings']['recovery_plan']!=read_json(pin(candidate['original_plan']))['recovery_plan'],
            'CORRECTED_INSTALLATION_REQUIRED')
    require(not (HERE/'work-plan.json').exists() and not (HERE/'paid-work').exists(),'SUCCESSOR_ALREADY_SELECTED')
    seed=convert(read_json(pin(candidate['history'])),authority,candidate)
    plan['request_ids']=IDS
    plan['budget']={'limit':500000,'preventive':480000,'initial_reserve':50000,'next_input_multiplier':2,'next_output_margin':32000}
    plan['successor_candidate']=ref(HERE/'candidate.json');plan['budget_authorization']=ref(a.authorization_record)
    plan['successor']={'namespace':str(HERE/'paid-work'),'new_requests':2,'global_max_requests':4,
        'historical_observed_tokens':144004,'historical_charged_requests':2,
        'old_conditional_continuation04_ineligible':True,'no_refund':True,'force_selected':False}
    plan['predecessor_paid_plan']=candidate['original_plan']
    plan['accounting']='Carry 144004 / 2 charges unchanged; authorized cumulative500000, preventive480000; at most two new requests, each separately checked with the original reserve formula.'
    # Retain the old dependency pins until the lifecycle owner supplies qualified
    # replacements explicitly. The actual installed-prefix guard remains in Context.
    old=read_json(pin(read_json(pin(candidate['original_plan']))['work_runtime_freeze']))
    files={name:ref(HERE/name) for name in ('sonnet_usage.py','remote_work.py','observe_active.py','activecontrol.py','request_context.py','reused_observation.py','successor_policy.py')}
    manifest={'files':files,'dependencies':old['dependencies'],'original_freeze':read_json(pin(candidate['original_plan']))['work_runtime_freeze']}
    reserve(HERE/'budget-seed-approved.json',seed)
    reserve(HERE/'work-runtime-freeze.json',manifest)
    plan['budget_seed']=ref(HERE/'budget-seed-approved.json');plan['work_runtime_freeze']=ref(HERE/'work-runtime-freeze.json')
    plan['runtime_pins']={name:ref(HERE/name) for name in ('work_context.py','work-entry.py','successor_policy.py')}
    reserve(HERE/'work-plan.json',plan)
    print(json.dumps({'state':'OFFLINE_PLAN_SELECTED_NO_EFFECT','plan':ref(HERE/'work-plan.json')}))

if __name__=='__main__':main()
