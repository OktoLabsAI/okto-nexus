"""Connect the already-planned operator step to eight frozen drivers; no runtime execution."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as E
R=Path(__file__).resolve().parent;D=R/'draft';S=Path(r'C:/Users/jpamb/AppData/Local/Temp/m1-v11-operator-candidate-sqp53mdk')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
assert sha(S/'runtime-pins.json')=='b29a20451c5e5ef84863267a37182b42baad0e963ccf76c75072c75ff15ca0ff'
assert sha(S/'qualification.json')=='4f96f65a0c5aedb464d92f0180e8adf01a91e1578ef4094151690c4cdf9781ec'
pins=read(S/'runtime-pins.json');assert len(pins)==8 and all(sha(v['path'])==v['sha256'] for v in pins.values())
cases=E.parse(S/'pure-tests-003.xml').getroot().findall('.//testcase');assert len(cases)==78 and all(c.find(t) is None for c in cases for t in ('failure','error','skipped'))
P=D/'m1-codex-campaign-proposal-v11.json';p=read(P)
p['execution_bundle']['files'].update(pins);assert len(p['execution_bundle']['files'])==46
recipe=read(D/'remote-canonical-recipe.json')
recipe.update(status='FROZEN_V11_RECIPE_WITH_EXECUTABLE_OPERATOR_STAGE_NOT_EXECUTED',
    conclusion='Qualified v11 metadata and reachable operator-bootstrap executor. Existing standing user authorization will be bound technically by root after final review; no HTTP, operator account, credential access, service or provider effect occurred during preparation.')
recipe['operator_bootstrap'].update(implementation_status='FROZEN_DRIVER_QUALIFIED',
    executor={'key':'root_driver_operator_bootstrap','path':pins['root_driver_operator_bootstrap']['path'],'sha256':pins['root_driver_operator_bootstrap']['sha256'],
        'invoke_mode':'operator_bootstrap','invoke_selection':['once']})
write(D/'remote-canonical-recipe.json',recipe)
planning=read(D/'planning-commands.json');planning.update(status='FROZEN_REFERENCE_STANDING_AUTHORIZATION_TECHNICAL_BINDING_PENDING')
planning['remote_recipe']={'path':str(D/'remote-canonical-recipe.json'),'sha256':sha(D/'remote-canonical-recipe.json')};write(D/'planning-commands.json',planning)
commands=read(D/'proposed-commands.json');commands['status']='FROZEN_EIGHT_ACTIONS_STANDING_AUTHORIZATION_TECHNICAL_BINDING_PENDING';write(D/'proposed-commands.json',commands)
for key,name in [('remote_canonical_recipe','remote-canonical-recipe.json'),('planning_commands','planning-commands.json')]:p['execution_bundle']['files'][key]={'path':str(D/name),'sha256':sha(D/name)}
p['execution_bundle']['commands']={'path':str(D/'proposed-commands.json'),'sha256':sha(D/'proposed-commands.json')}
p['execution_bundle']['status']='FROZEN_QUALIFIED'
p['execution_bundle']['final_gate_reports']=[str(R/'operator-final-entry-gates/results.xml'),str(R/'operator-final-entry-gates/result.json')]
p['execution_bundle']['qualification_scope']='Unchanged64 controller/CLI,30 fake installer,22 remote and7 lifecycle cases retained;78 final driver cases replace51 predecessor driver cases. New46-pin isolated origin/metadata verification and20 real Python entry denials recorded separately. No real campaign execution.'
p['operator_bootstrap'].update(implementation_status='FROZEN_DRIVER_BOUND_OFFLINE_QUALIFIED',driver_key='root_driver_operator_bootstrap',
    invocation=[p['package_pins']['python'],'-I','-B',pins['root_driver_invoke']['path'],'--proposal',str(P),
        '--expected-proposal-sha256','<EXACT_FINAL_V11_PROPOSAL_SHA256>','--approval-path','<V11_TECHNICAL_BINDING_PATH>',
        '--approval-sha256','<V11_TECHNICAL_BINDING_SHA256>','operator_bootstrap','once'],
    stage='After settled local setup/useful/continuation and before remote plan/transfer; controller is loaded, never reset.',
    model_admissions=0)
step=next(v for v in p['steps'] if v['id']=='05-connector-root-review-finish')
step['commands']=[v for v in step['commands'] if '<NEXUS> operator login' not in v]
step['commands'].insert(0,'<PINNED_ROOT_INVOKE> <technical binding selectors> operator_bootstrap once')
step['operator_executor']='root_driver_operator_bootstrap through the finite invoke selection; own account POST and canonical password-stdin login/status while existing accounting remains monitored.'
p['root_driver_preparation'].update(status='EIGHT_FROZEN_OFFLINE_DRIVERS_BOUND_NOT_EXECUTED',pins=str(S/'runtime-pins.json'),pins_sha256=sha(S/'runtime-pins.json'),qualification=str(S/'qualification.json'),qualification_sha256=sha(S/'qualification.json'),unique_cases=78)
p.update(status='FINAL_ARTIFACTS_READY_FOR_ROOT_REVIEW_TECHNICAL_BINDING_PENDING',qualification_status='OPERATOR_COMPLETED_UNCHANGED_COMPONENTS_RETAINED_AFFECTED_CHECKS_RECORDED_SEPARATELY',final_proposal=True,execution_authorized=False)
p['blocking_preconditions']=['Root final frozen-byte/scope review and a truthful v11 technical record linking the standing user authorization; no new human hash-approval request.',
    'Successful one-shot installation proof and fresh exact own task/home/port/native preflight before campaign effects.']
p['controller_preparation']['composed_module_origins']={'path':str(R/'operator-final-origins/module-origins.json'),'verification_pending':True}
groups=read(D/'offline-finalization.json')['groups'];groups['root-driver-component']={'tests':78,'xml':str(S/'pure-tests-003.xml'),'xml_sha256':sha(S/'pure-tests-003.xml')}
p['controller_preparation']['qualification_groups']=groups
write(P,p)
final=read(D/'offline-finalization.json');final.update(status=p['status'],proposal_sha256=sha(P),groups=groups,runtime_pins=46,
    standing_user_authorization=True,new_human_hash_approval_required=False,technical_v11_binding_created=False,
    predecessor_attempt_manifest_sha256=sha(R/'public/artifact-manifest.json'))
write(D/'offline-finalization.json',final)
print(json.dumps({'proposal_sha256':sha(P),'runtime_pins':46,'driver_cases':78,'standing_authorization':True,'real_effects':0}))
