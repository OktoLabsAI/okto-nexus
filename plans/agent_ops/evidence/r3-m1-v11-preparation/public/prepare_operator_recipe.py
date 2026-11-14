"""Correct the existing v11 recipe and preserve the pre-operator-fix attempt; no runtime effects."""
from pathlib import Path
import copy,hashlib,json
R=Path(__file__).resolve().parent;D=R/'draft';H=D/'preparation-history/before-operator-fix'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
P=D/'m1-codex-campaign-proposal-v11.json'
assert sha(P)=='fbc181746c253193b11bac6fa48b7b124a9b79755499340b6fdee6709689fff7'
assert sha(R/'public/artifact-manifest.json')=='ccb58d570517a447c4966f73ba1348fb3161cecaffbf726719b50a1b0df09199'
assert not (R/'campaign').exists() and not H.exists()
H.mkdir(parents=True)
for name in ('m1-codex-campaign-proposal-v11.json','remote-canonical-recipe.json','planning-commands.json','offline-finalization.json'):
    (H/name).write_bytes((D/name).read_bytes())
review=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v11-root-review.json')
assert review.exists();(H/'root-review-before-operator-fix.json').write_bytes(review.read_bytes())
write(H/'historical-attempt.json',{'status':'HISTORICAL_ATTEMPT_NOT_AUTHORIZED_OPERATOR_STAGE_MISSING',
    'proposal_sha256':sha(H/'m1-codex-campaign-proposal-v11.json'),
    'public_manifest_sha256':sha(R/'public/artifact-manifest.json'),'public_qualification_sha256':sha(R/'public/qualification.json'),
    'root_preflight_sha256':sha(review),'root_preflight_is_current_approval':False,
    'limitations':['Recipe retained v10 policy/authority labels.','Planned operator account/bootstrap/login did not have a reachable frozen executor.'],
    'public209_modified':False,'effects_executed':0})
p=read(P);recipe=read(D/'remote-canonical-recipe.json')
recipe.update(format='m1-v11-readonly-remote-recipe',proposal_revision=11,status='V11_RECIPE_PENDING_FROZEN_OPERATOR_DRIVER_NOT_EXECUTED',
    authority='Finite v11 recipe only. Execution requires the real exact v11 approval receipt and the final proposal SHA supplied to the pinned driver; no v10 or earlier authorization is inherited.',
    conclusion='Static v11 sequence and qualified-product reference review only. No HTTP, provider, real account, credentials, services or product command executed. The newly connected operator step remains pending frozen implementation qualification and final review.')
recipe['proposal']={'path':str(P),'sha256':'<EXACT_FINAL_V11_PROPOSAL_SHA256>'}
recipe['limits']={'policy':copy.deepcopy(p['controller_preparation']['policy']),
    'preparation_only':{'product_commands_executed':0,'http_requests':0,'personal_credentials_read':0,'services_mutated':0,'checkout_changed':False},
    'runtime_scope':'After exact authorization only: bounded own loopback account/bootstrap and canonical operator login/status, while the existing global controller continues historical accounting. No productive model reservation is added.'}
recipe['operator_bootstrap'].update(implementation_status='PENDING_FROZEN_V11_OPERATOR_DRIVER',
    stage='After settled local setup/useful/continuation, before remote plan and protected transfer.',
    controller='Existing campaign/private/controller.json only (create=False); reattach historical work/setup observations and require current empty/can_admit before phase. No baseline reset or new productive reservation.',
    monitoring='Keep the existing owner accounting loop and effect fence active throughout bounded HTTP and login/status subprocesses. Preserve120-second phase deadline and600ms aggregate/1s freshness; do not emit secrets in metadata.',
    productive_model_turns=0)
site=Path(p['package_pins']['qualified_reference_environment'])/'Lib/site-packages'
payloads={Path(item['path']).relative_to(D/'installation/venv/Lib/site-packages').as_posix():item['sha256']
    for item in p['package_pins']['files'] if Path(item['path']).is_relative_to(D/'installation/venv/Lib/site-packages')}
sources=[]
for old in recipe['source_hashes']:
    parts=Path(old['path']).parts;relative=Path(*parts[parts.index('src')+1:])
    source=site/relative;assert sha(source)==payloads[relative.as_posix()]
    sources.append({'path':str(source),'sha256':sha(source),'basis':'unchanged qualified installed reference product, matching campaign wheel payload'})
recipe['source_hashes']=sources
recipe['source_ancestry']['change']='Earlier v10 recipe retained as history; current v11 root/labels/authority/policy corrected and the already-planned operator step is being connected to an explicit frozen driver.'
write(D/'remote-canonical-recipe.json',recipe)
planning=read(D/'planning-commands.json');planning['remote_recipe']={'path':str(D/'remote-canonical-recipe.json'),'sha256':sha(D/'remote-canonical-recipe.json')}
planning['status']='OPERATOR_DRIVER_COMPLETION_PENDING_NOT_AUTHORIZED';write(D/'planning-commands.json',planning)
p.update(status='OPERATOR_DRIVER_COMPLETION_PENDING_NOT_AUTHORIZED',qualification_status='UNCHANGED_COMPONENTS_QUALIFIED_OPERATOR_STAGE_PENDING',execution_authorized=False,final_proposal=False)
p['execution_bundle']['status']='PENDING_OPERATOR_DRIVER_COMPLETION'
for key,name in [('remote_canonical_recipe','remote-canonical-recipe.json'),('planning_commands','planning-commands.json')]:
    p['execution_bundle']['files'][key]={'path':str(D/name),'sha256':sha(D/name)}
p['operator_bootstrap']['implementation_status']='PENDING_EXPLICIT_FROZEN_DRIVER_AND_AFFECTED_OFFLINE_GATES'
write(P,p)
print(json.dumps({'status':p['status'],'recipe_sha256':sha(D/'remote-canonical-recipe.json'),'public209_unchanged':True,'qualified_source_references':len(sources)}))
