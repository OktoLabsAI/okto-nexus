from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parent;D=R/'draft';DR=R/'root-drivers';SRC=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-presence-candidate-y6vdz9jf')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
f=SRC/'runtime-freeze.json';assert sha(f)=='9629f65336fd3c7b011470c7c712fa5b10dd1c20ab2b6fddbde5c51b3d9ce691';freeze=read(f)
for section in ('runtime','tests'):
 for name,item in freeze[section].items():
  source=Path(item['path']);assert sha(source)==item['sha256'];shutil.copyfile(source,DR/name);assert sha(DR/name)==item['sha256']
for name in ('runtime-freeze.json','qualification.json','README.md'):
 if (SRC/name).exists():shutil.copyfile(SRC/name,DR/name)
p=read(D/'m1-codex-campaign-proposal-v12.json')
for key,pin in p['execution_bundle']['files'].items():
 if key.startswith('root_driver_'):pin['sha256']=sha(pin['path'])
recipe=read(D/'remote-canonical-recipe.json');recipe['operator_bootstrap']['executor'].update(p['execution_bundle']['files']['root_driver_operator_bootstrap']);recipe['status']='FROZEN_V12_RECIPE_WITH_EXECUTABLE_OPERATOR_STAGE_NOT_EXECUTED';write(D/'remote-canonical-recipe.json',recipe)
planning=read(D/'planning-commands.json');planning['remote_recipe']['sha256']=sha(D/'remote-canonical-recipe.json');write(D/'planning-commands.json',planning)
for pin in p['execution_bundle']['files'].values():pin['sha256']=sha(pin['path'])
q=read(SRC/'qualification.json')
xml=next(x for x in SRC.glob('*.xml') if sha(x)==q['tests_sha256'])
p['root_driver_preparation']={'status':'V12_DRIVER_COMPONENT_OFFLINE_QUALIFIED','source_freeze':{'path':str(f),'sha256':sha(f)},'qualification':{'path':str(SRC/'qualification.json'),'sha256':sha(SRC/'qualification.json')},'tests':121,'xml':str(xml),'xml_sha256':sha(xml),'files':8,
 'cleanup':'Strict completed local setup failure can prove Connector never selected from exact returned invocation inventory, sealed checkpoint local1/work0, pristine remote/operator roots and canonical absent/task/port proof. Connector absence preserves raw generation empty string plus running/ipc false; no unknown normalization.'}
p['controller_preparation']['composed_module_origins']={'path':str(R/'final-origins/module-origins.json'),'verification_pending':True}
p['execution_bundle']['final_gate_reports']={'result':str(R/'final-entry-gates/result.json'),'xml':str(R/'final-entry-gates/results.xml')}
p['status']='FINAL_COMPOSITION_AWAITING_ORIGIN_AND_ENTRY_CHECKS'
write(D/'m1-codex-campaign-proposal-v12.json',p)
groups={
 'retained-discovery-source':{'xml':'C:/Users/jpamb/AppData/Local/Temp/m1-v11-setup-discovery-candidate-nsuy793o/qualification/final.xml','xml_sha256':'467973bb394457528c9677f9967aaa500d0779ed59c6626f8f539ad53268e322','scope':'73PASS;1 historical private DB case deselected. Source revision11 evidence, combined with V12 affected policy/identity checks; original64 not rerun.'},
 'v12-affected-composition':{'xml':str(R/'affected-composition-final/results.xml'),'xml_sha256':sha(R/'affected-composition-final/results.xml'),'scope':'76PASS:3allocation+10discovery+4workwrapper+30installer+22remote+7lifecycle; overlaps retained source counted once.'},
 'v12-root-drivers':{'xml':str(xml),'xml_sha256':sha(xml),'scope':'121PASS:78base+43strictlocalonly/representation cases; copied runtime bytes identical.'}}
write(D/'offline-finalization.json',{'status':'ORIGINS_AND_ENTRY_GATES_PENDING','groups':groups,'runtime_pins':46,'package_pins':984,'campaign_absent':True,'products_not_installed':True,'technical_v12_binding_created':False})
print(json.dumps({'copied_runtime':len(freeze['runtime']),'copied_tests':len(freeze['tests']),'driver_cases':121,'xml':str(xml)}))
