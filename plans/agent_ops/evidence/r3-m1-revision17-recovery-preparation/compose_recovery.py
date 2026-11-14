from pathlib import Path
from copy import deepcopy
import hashlib,json
H=Path(__file__).resolve().parent;OLD=H.with_name('work-revision17')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8',newline='\n')
A=read(OLD/'amendment.json')
assert sha(OLD/'runtime-freeze.json')=='5dba520a68d87cf71dd9135b0d73dba0e6b1283515ff96246369f3e558cfb9c4'
assert sha(OLD/'public/closure.json')=='a2d7c6d8a50f92ba2cdebe0a3fc12def193175f720ee1b3093474d01e55f7ad4'
assert sha(OLD/'private/controller.json')=='73e792d6928e379f82cf1f97b08e524c71c0bdd9c63d0bc9c8b96b4f1bd49681'
assert read(OLD/'private/controller.json')['requests']=={}
assert sha(A['initial_work_checkpoint']['path'])==A['initial_work_checkpoint']['sha256']
assert not any((H/n).exists() for n in ('public','private','runtime-private','package'))
files={'checkpoint':pin(OLD/'private/controller.json'),'closure':pin(OLD/'public/closure.json'),
 'failure':pin(OLD/'public/authorize-local-review-unconfirmed.json'),'final_presence':pin(OLD/'public/final-presence.json'),
 'exit_proof':pin(OLD/'public/nexus-exit-proof.json'),'cleanup':pin(OLD/'public/cleanup-nexus.json'),
 'diagnosis':pin(Path('C:/Users/jpamb/AppData/Local/Temp/m1-w17-review-checkpoint-diagnosis-mwwdr2ou/diagnosis.json')),
 'original_freeze':pin(OLD/'runtime-freeze.json'),'original_amendment':pin(OLD/'amendment.json')}
assert files['diagnosis']['sha256']=='1eb8b45d1210f5c57d7467014fca70b0b4607ef5196c4630e6bb597e0fe788a8'
reservations={p.name:pin(p) for p in sorted((OLD/'runtime-private').glob('*.reserved.json'))}
assert set(reservations)=={'authorize_local-review.reserved.json','lifecycle-nexus-install.reserved.json','lifecycle-nexus-start.reserved.json','lifecycle-nexus-uninstall.reserved.json'}
proof={'status':'CLOSED_PRE_REVIEW_FAILURE_ZERO_AUTHORIZATION_API','root':str(OLD),'files':files,
 'reservations':reservations,'returns':{name:pin(Path(v['path']).with_name(name.replace('.reserved.json','.returned.json'))) for name,v in reservations.items()},
 'same_paid_basis':A['basis']['checkpoint'],'old_fault_preserved':True,'refund':False,'new_paid_request':False}
save(H/'closed-preflight.json',proof)
recovery={'status':'ROOT_SELECTED_OFFLINE_RECOVERY_NOT_EXECUTED','work_root':str(H),'base_plan':A['execution_plan'],
 'base_amendment':pin(OLD/'amendment.json'),'base_freeze':pin(OLD/'runtime-freeze.json'),'closed_preflight':pin(H/'closed-preflight.json'),
 'policy':A['policy'],'request_ids':A['request_ids'],'remote_execution_enabled':False,
 'scope':'Same unselected request15/16, budget/prompt/package. Fresh namespace for one canonical review after exact historical review guard; no paid restart/reset, no manual checkpoint edits.',
 'pre_review_delta':'Permit only pinned historical state=review with valid document revision and expected scope; refuse submitted/unknown; installed authorization_review creates a fresh review request and saves it canonically.',
 'effects_before_review':0,'new_human_hash_approval_claimed':False,'future_force_authorized':False}
save(H/'recovery-plan.json',recovery)
value=deepcopy(A)
value.update(format='okto.m1.v17.work-revision17-recovery',work_root=str(H),native_decision_path=str(H/'private/native-decision.json'),
 recovery_plan=pin(H/'recovery-plan.json'),closed_preflight=pin(H/'closed-preflight.json'),
 scope='Recovery of closed pre-review failure only; same local15/16 IDs and paid W16 basis, original W17 fault retained as mandatory operational history.')
value['sources']={k:pin(H/Path(v['path']).relative_to(OLD)) for k,v in A['sources'].items()}
value['bundle_overrides']={k:pin(H/Path(v['path']).relative_to(OLD)) for k,v in A['bundle_overrides'].items()}
value['basis']={**A['basis'],'controller_freeze':pin(H/'controller-qualification/runtime-freeze.json'),
 'operational_preflight':pin(H/'closed-preflight.json'),'recovery_plan':pin(H/'recovery-plan.json')}
# All five paid histories, original failed preflight and token/admission accounting remain pinned.
value['technical_supersession']={**A['technical_supersession'],'failed_preflight':pin(H/'closed-preflight.json'),
 'new_technical_paid_allocation':False,'recovery_namespace_only':True,'original_failure_erased':False}
save(H/'amendment.json',value)
print(json.dumps({'amendment_sha256':sha(H/'amendment.json'),'recovery_plan_sha256':sha(H/'recovery-plan.json')}))
