from pathlib import Path
import hashlib,importlib.util,json
R=Path(__file__).resolve().parent;D=R/'draft';I=D/'installation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
def labels(v):
 if isinstance(v,str):return v.replace('proposal-v11.json','proposal-v12.json')
 if isinstance(v,list):return [labels(x) for x in v]
 if isinstance(v,dict):return {k:labels(x) for k,x in v.items()}
 return v
for name in ('m1-codex-campaign-proposal-v12.json','remote-canonical-recipe.json','planning-commands.json','proposed-commands.json'):
 write(D/name,labels(read(D/name)))
f=D/'test_preparation_entries.py';f.write_bytes(f.read_text().replace('proposal-v11.json','proposal-v12.json').encode())
p=read(D/'m1-codex-campaign-proposal-v12.json')
for obj,key in ((p['authorization'],'scope'),(p['base06_installation'],'guard'),(p['execution_bundle'],'gate')):obj[key]=obj[key].replace('v11','v12')
p['scope_qualification']['allocation_test_clock']=p['scope_qualification']['allocation_test_clock'].replace('eleven-cumulative','twelve-cumulative')
p['scope_qualification']['status']='OFFLINE_INSTALLED_CLI_PARSER_HANDLERS_INHERITED_V12_COMPOSITION_PENDING_REAL_M1_PENDING'
p['root_driver_preparation']={'status':'V12_CLEANUP_CANDIDATE_PENDING','historical_v11_qualification':'78_PASS_RETAINED_NOT_RELABELED_V12'}
recipe=read(D/'remote-canonical-recipe.json');recipe['authority']=recipe['authority'].replace('v11 artifacts','v12 artifacts')
recipe['operator_bootstrap']['executor']={'key':'root_driver_operator_bootstrap',**p['execution_bundle']['files']['root_driver_operator_bootstrap'],'invoke_mode':'operator_bootstrap','invoke_selection':['once']}
write(D/'remote-canonical-recipe.json',recipe)
planning=read(D/'planning-commands.json');planning['remote_recipe']={'path':str(D/'remote-canonical-recipe.json'),'sha256':sha(D/'remote-canonical-recipe.json')};write(D/'planning-commands.json',planning)
for key,pin in p['execution_bundle']['files'].items():
 f=Path(pin['path']);assert f.is_file(),(key,f);pin['sha256']=sha(f)
p['execution_bundle']['commands']['sha256']=sha(D/'proposed-commands.json')
for key,name in (('controller_sha256','controller.py'),('collector_sha256','token_collector.py'),('observer_sha256','independent_controller.py')):p['controller_preparation'][key]=sha(D/'controller'/name)
spec=importlib.util.spec_from_file_location('timed_install_v12_metadata',I/'timed_install.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.ROOT==I and m.CAMPAIGN==R/'campaign'
assert m.POLICY==p['controller_preparation']['policy'] and m.ANCESTRY==p['controller_preparation']['ancestry']
p['base06_installation'].update(m.artifact_pins())
p['base06_installation'].update(dependencies_prepared=True,products_installed=False,dependency_preparation_sha256=sha(I/'dependency-preparation.json'),direct_interpreter_qualification='PASS_OWN_BASE_PID_AND_VENV_PREFIX_PRODUCTS_ABSENT')
p['package_pins']['files'][-1]={'path':str(I/'venv/Scripts/python.exe'),'sha256':sha(I/'venv/Scripts/python.exe')}
assert len(p['package_pins']['files'])==984
p['controller_preparation']['affected_composition']={'xml':str(R/'affected-composition-final/results.xml'),'sha256':sha(R/'affected-composition-final/results.xml'),'tests':76,'scope':'3 allocation+10 discovery+4 workwrapper+30 installer+22 remote+7 lifecycle. Historical source64 not rerun. First collection error preserved separately.'}
write(D/'m1-codex-campaign-proposal-v12.json',p)
old=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z')
s=(old/'verify_operator_final_origins.py').read_text().replace('proposal-v11.json','proposal-v12.json').replace('operator-final-origins','final-origins')
s=s.replace("POLICY['revision']==11","POLICY['revision']==12").replace("POLICY['carry_in_admissions']==6","POLICY['carry_in_admissions']==7").replace("POLICY['max_cumulative_admissions']==11","POLICY['max_cumulative_admissions']==12")
(R/'verify_final_origins.py').write_bytes(s.encode())
s=(old/'qualify_operator_final_gates.py').read_text().replace('proposal-v11.json','proposal-v12.json').replace('operator-final-entry-gates','final-entry-gates')
s=s.replace('m1-v11-readonly-remote-recipe','m1-v12-readonly-remote-recipe').replace("recipe['proposal_revision']==11","recipe['proposal_revision']==12")
(R/'qualify_final_gates.py').write_bytes(s.encode())
print(json.dumps({'runtime_pins':len(p['execution_bundle']['files']),'payload_pins':len(p['package_pins']['files']),'metadata_ready_driver_freeze_pending':True}))
