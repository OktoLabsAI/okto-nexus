"""Future metadata-only binding; never starts a service or manufactures a receipt."""
from pathlib import Path
import argparse,json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from post_context import RECOVERY,LIFECYCLE_SHA,RecoveryContext,verify_freeze,validate_basis,require,read_json,sha,reserve

def make_plan(freeze_sha,svc20_sha,result_sha):
    verify_freeze(freeze_sha)
    base=RecoveryContext(RECOVERY/'lifecycle-plan.json',LIFECYCLE_SHA)
    source=RECOVERY/'svc20-next-connect';public=source/'public'
    paths={'svc20_plan':source/'selected-plan.json','svc20_result':public/'result.json','before':public/'before.json',
      'after_connect':public/'after-connect-cohort.json','initial_exit':public/'initial-stop-exit-proof.json',
      'final_exit':public/'final-stop-exit-proof.json','completed':RECOVERY/'public/recovery02-profile-completed.json',
      'rotation':RECOVERY/'public/rotation-import-result.json','migration':RECOVERY/'public/connector-upgrade-apply-returned.json'}
    refs={k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()}
    require(refs['svc20_plan']['sha256']==svc20_sha and refs['svc20_result']['sha256']==result_sha,'ROOT_REVIEWED_SVC20_CHANGED')
    migrated=read_json(paths['migration']);cohort=read_json(paths['after_connect'])
    plan={'status':'ROOT_SELECTED_AFTER_REAL_SVC20_ZERO_ADMISSIONS','scope':'ONE_CONNECTOR_START_FRESH_COHORT_NO_REINSTALL',
       'runtime_freeze_sha256':freeze_sha,'basis':refs,'task_digest':cohort['task']['digest'],
       'migrated_context_sha256':migrated['target_context_sha256'],'lifecycle_plan_sha256':LIFECYCLE_SHA,
       'nexus_public':str(RECOVERY/'public'),'connector_public':str(HERE/'public'),'connector_private':str(HERE/'private'),
       'provider_calls_selected':0,'install_selected':False,'old_receipts_preserved':True,'max_start_selections':1,
       'cleanup_scope':'Current selected Connector cohort only; later paid work requires its own canonical interruption/settlement. No force or restart replay.'}
    validate_basis(plan,base)
    require(sha(base.P['source_contexts']['connector']['path'])==plan['migrated_context_sha256'],'MIGRATED_CONTEXT_CHANGED')
    return plan

def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime-freeze-sha256',required=True)
    p.add_argument('--svc20-plan-sha256',required=True);p.add_argument('--svc20-result-sha256',required=True);a=p.parse_args()
    plan=make_plan(a.runtime_freeze_sha256,a.svc20_plan_sha256,a.svc20_result_sha256)
    reserve(HERE/'selected-plan.json',plan)
    print(json.dumps({'selected_plan_sha256':sha(HERE/'selected-plan.json'),'service_effects':0,'provider_calls':0}))
if __name__=='__main__':main()
