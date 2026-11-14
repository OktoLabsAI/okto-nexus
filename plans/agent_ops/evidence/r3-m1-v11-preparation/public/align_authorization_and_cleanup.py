"""Correct assistant-authored authorization wording and align the already-qualified cleanup route."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent;D=R/'draft';P=D/'m1-codex-campaign-proposal-v11.json'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
p=read(P);recipe=read(D/'remote-canonical-recipe.json');commands=read(D/'proposed-commands.json')
auth_path=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v10-approved-execution/authorization.json')
historical=read(auth_path)
review={'status':'STANDING_USER_AUTHORIZATION_CONFIRMED_BY_ROOT_NO_NEW_HASH_APPROVAL_REQUIRED',
    'historical_receipt':str(auth_path),'historical_receipt_sha256':sha(auth_path),
    'actual_user_quote':historical['user_quote'],
    'assistant_authored_interpretation':historical['interpretation'],'assistant_authored_scope':historical['scope'],
    'finding':'The available human messages authorize continuing the work; no explicit human restriction to v10 or exclusion of another necessary finite cycle was found. The exact-v10-only and new-human-hash-approval restrictions came from assistant-authored artifact interpretation.',
    'root_resolution':'Continue preparation under the standing authorization and unchanged material limits. After final freeze/review, root may create a truthful v11 technical binding to that authorization, without claiming the user textually approved the artifact hash.',
    'not_authorized':['forced service stop','logout/reboot','personal-file/authentication-file access by the assistant','old intent replay or accounting reset','budget increase'],
    'v10_receipt_modified':False,'v11_technical_binding_created':False,'effects_executed':0}
write(D/'authorization-origin-review.json',review)
p['authorization']={'execution_authorized':False,'standing_user_authorization_received':True,
    'new_human_approval_of_hash_required':False,'direct_user_approval_of_this_hash_claimed':False,
    'technical_v11_binding_created':False,'approval_receipt_created':False,
    'scope':'The existing user authorization covers necessary continuation within the recorded budgets/material scope. Dispatch remains technically blocked until final freeze/root review and a v11 record binds those standing instructions to the exact artifacts. Earlier v10 receipts stay historical and are not replayed.'}
p['blocking_preconditions']=['Complete and qualify the already-planned operator bootstrap executor.',
    'Root final review and technical v11 binding to the existing user authorization; no new human hash-approval request is required.',
    'Successful one-shot installation proof and fresh exact own task/home/port/native preflight before campaign effects.']
p['execution_bundle']['gate']='A truthful v11 technical record binds the existing user authorization to final reviewed bytes, limits and own roots. Unchanged pins and one-shot installation proof still precede every effect; this is not a new human approval requirement.'
p['base06_installation']['guard']='Standing user authorization already exists. Final artifact freeze/root review and the exact v11 technical binding precede any reservation; existing or unknown reservations remain non-replayable. No installation has executed.'
recipe['authority']='The existing user authorization covers continuation within the unchanged recorded material scope/budgets. Runtime requires final reviewed v11 artifacts and a truthful technical receipt binding that authorization to the exact proposal SHA. No new human approval of the hash is required; prior v10 artifact receipts remain historical and cannot be mechanically reused or replayed.'
recipe['protected_transfer']['argv_template']=[v.replace('<actual approved receipt path>','<v11 technical authorization binding path>').replace('<actual approved receipt SHA256>','<v11 technical authorization binding SHA256>') for v in recipe['protected_transfer']['argv_template']]
recipe['close_and_get_recovery']=[{
    'lane':lane,'component':component,'work_close_dispatch':False,
    'normal_stop':'Use the existing pinned lifecycle wrapper selection '+component+' stop once, with the same v11 technical binding.',
    'qualified_steps':[step for step in commands['steps'] if step['component']==component and step['action'] in ('stop','uninstall')],
    'success_oracle':['Exact owned generation/instance and retained PID/birth handle physically exited.',
        'Canonical shutdown record DRAINED and expected task stopped with unchanged identity/digest.',
        'Existing pinned cleanup validator confirms proof before the single uninstall; action/result bind cleanup proof SHA.',
        'Final presence/closure drivers retain accounting and require owned process/task absence; no per-work close-intent receipt is invented.'],
    'uncertainty':'Keep unknown state and retained observations. No forced service stop, replay, restart or extra lifecycle action.'}
    for lane,component in [('local','nexus'),('connector','connector')]]
step=p['steps'][-1];assert step['id']=='08-close-drain-cleanup'
step['commands']=[f"<QUALIFIED_LIFECYCLE_WRAPPER> {item['component']} {item['action']}" for item in commands['steps'] if item['action'] in ('stop','uninstall')]
step['required_evidence']='Qualified normal component stop/drain, exact owned PID/birth exit and task proof, one uninstall tied to cleanup proof hash, final retained accounting and absence. No separately dispatched work-close control intent or receipt is claimed.'
step['dispatch_rule']='Use only the existing pinned lifecycle and cleanup/presence/closure drivers; no additional work-close driver, gate or service action is introduced.'
step.pop('coverage_limit',None)
write(D/'remote-canonical-recipe.json',recipe)
planning=read(D/'planning-commands.json');planning['remote_recipe']['sha256']=sha(D/'remote-canonical-recipe.json');write(D/'planning-commands.json',planning)
for key,name in [('remote_canonical_recipe','remote-canonical-recipe.json'),('planning_commands','planning-commands.json')]:
    p['execution_bundle']['files'][key]['sha256']=sha(D/name)
write(P,p)
assert sha(auth_path)==review['historical_receipt_sha256']
print(json.dumps({'status':p['status'],'new_human_approval_required':False,'receipt_created':False,'cleanup_route':'existing normal stop/drain drivers','recipe_sha256':sha(D/'remote-canonical-recipe.json')}))
