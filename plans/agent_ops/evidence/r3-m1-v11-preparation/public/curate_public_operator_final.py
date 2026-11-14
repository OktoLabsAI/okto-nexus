"""Allowlisted offline metadata/source evidence only; excludes environments and campaign data."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as E
R=Path(__file__).resolve().parent;D=R/'draft';OUT=R/'public-operator-final'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
assert not OUT.exists() and not (R/'campaign').exists()
proposal=D/'m1-codex-campaign-proposal-v11.json';p=read(proposal)
assert p['execution_bundle']['status']=='FROZEN_QUALIFIED' and not p['execution_authorized']
final=read(R/'operator-final-entry-gates/result.json')
assert final['exit_code']==0 and final['inputs_unchanged'] and final['proposal_sha256']==sha(proposal)
assert final['campaign_root_absent'] and final['installation_unreserved']
assert read(R/'operator-final-entry-gates/actual-input-verification.json')['status']=='PASS'
groups={};unique=set()
input_groups=read(D/'offline-finalization.json')['groups']
input_groups['operator-final-entry-gates']={'xml':str(R/'operator-final-entry-gates/results.xml'),'xml_sha256':sha(R/'operator-final-entry-gates/results.xml')}
for name,entry in input_groups.items():
    xml=Path(entry['xml']);assert sha(xml)==entry['xml_sha256']
    cases=E.parse(xml).getroot().findall('.//testcase')
    assert all(not any(c.find(tag) is not None for tag in ('failure','error','skipped')) for c in cases)
    identities={(c.attrib['classname'],c.attrib['name']) for c in cases}
    assert len(identities)==len(cases);unique.update(identities)
    groups[name]={'tests':len(cases),'failures':0,'errors':0,'skipped':0,'xml_sha256':sha(xml),
        'artifact':xml.relative_to(R).as_posix() if xml.is_relative_to(R) else 'component-evidence/'+name+'/results.xml'}
assert len(unique)==221
selected=set(R.glob('*.py'))|set(D.glob('*.py'))|set(D.glob('*.json'))
selected.update((D/'controller').glob('*.py'))
selected.update((D/'protected-transfer').glob('*.py'))
selected.update((D/'diffs').glob('*.diff'))
selected.update((R/'observer-composition-initial/sources').rglob('*.py'))
selected.update((R/'observer-composition-final/sources').rglob('*.py'))
selected.update(x for x in (D/'preparation-history').rglob('*') if x.is_file())
for name in ('timed_install.py','prepare_dependencies.py','probe_direct_interpreter.py','test_timed_install.py',
    'products-requirements.txt','dependency-manifest.json','dependency-preparation.json','direct-interpreter-final.json'):
    selected.add(D/'installation'/name)
for group in ('installer-checks','remote-composition-final','lifecycle-cleanup-checks','operator-final-entry-gates','observer-composition-initial','observer-composition-final','final-composed-origins','operator-final-origins','reviewed-final-entry-gates'):
    for name in ('result.json','results.xml','stdout.txt','stderr.txt','module-origins.json','actual-input-verification.json'):
        source=R/group/name
        if source.exists():selected.add(source)
assert all(x.is_relative_to(R) and 'venv' not in x.parts and 'campaign' not in x.parts and 'pytest-tmp' not in x.parts for x in selected)
OUT.mkdir();records=[]
for source in sorted(selected):
    relative=source.relative_to(R);target=OUT/relative;target.parent.mkdir(parents=True,exist_ok=True)
    before=sha(source);target.write_bytes(source.read_bytes());assert sha(source)==sha(target)==before
    records.append({'path':relative.as_posix(),'source_sha256':before,'artifact_sha256':before,'bytes':target.stat().st_size})
external={}
for name,entry in input_groups.items():
    source=Path(entry['xml'])
    if not source.is_relative_to(R):external['component-evidence/'+name+'/results.xml']=source
source_freeze=Path(p['controller_preparation']['source_freeze']['path'])
for name in ('qualification.json','runtime-freeze.json','real-closed-db-evidence.json','predecessor-cli-final.xml','predecessor-timing-failures.json'):
    source=source_freeze.parent/name
    if source.exists():external['component-evidence/installed-controller-cli-component/'+name]=source
driver_dir=Path(p['execution_bundle']['files']['root_driver_common']['path']).parent
for key,pin in p['execution_bundle']['files'].items():
    if key.startswith('root_driver_'):
        assert sha(pin['path'])==pin['sha256']
        external['root-drivers/'+Path(pin['path']).name]=Path(pin['path'])
for source in [*(driver_dir.glob('test*.py')),driver_dir/'qualification.json',driver_dir/'runtime-pins.json',driver_dir/'README.md']:
    if source.exists():external['root-drivers/'+source.name]=source
for relative,source in sorted(external.items()):
    target=OUT/relative;target.parent.mkdir(parents=True,exist_ok=True);digest=sha(source)
    assert not target.exists();target.write_bytes(source.read_bytes());assert sha(target)==sha(source)==digest
    records.append({'path':relative,'source_sha256':digest,'artifact_sha256':digest,'bytes':target.stat().st_size})
qualification={'status':'OFFLINE_V11_QUALIFIED_STANDING_AUTHORIZATION_TECHNICAL_BINDING_PENDING',
    'proposal_sha256':sha(proposal),'groups':groups,'unique_test_cases':len(unique),
    'source_freeze':p['controller_preparation']['source_freeze'],
    'scope_qualification':p['scope_qualification'],
    'source_attempts':'Selected source candidate history remains independently preserved; successful composition does not erase predecessor timing failures or prove real-time scheduling.',
    'product_build_scope':p['package_pins']['build_scope'],
    'policy':p['controller_preparation']['policy'],'ancestry':p['controller_preparation']['ancestry'],
    'product_payload_count':983,'all_package_pins':984,'runtime_pin_count':len(p['execution_bundle']['files']),
    'dependency_files':read(D/'installation/dependency-preparation.json')['dependency_files'],
    'lf_requirements_sha256':sha(D/'installation/products-requirements.txt'),
    'campaign_directory_created':False,'products_installed':False,'real_approval_created':False,'technical_v11_binding_created':False,'standing_user_authorization_received':True,'new_human_approval_of_hash_required':False,
    'provider_calls':0,'service_actions':0,'credentials_read':0,'m1_complete':False,
    'publication':'Allowlisted source and sanitized offline test evidence; no wheels, executable binaries, environment, databases, vault, live provider data or synthetic approval fixture directories.'}
write(OUT/'qualification.json',qualification)
digest=sha(OUT/'qualification.json');records.append({'path':'qualification.json','source_sha256':digest,'artifact_sha256':digest,'bytes':(OUT/'qualification.json').stat().st_size})
write(OUT/'artifact-manifest.json',{'schema':'m1.public-artifact-manifest','revision':1,'artifacts':records})
print(json.dumps({'public':str(OUT),'artifacts':len(records),'unique_tests':len(unique),'manifest_sha256':sha(OUT/'artifact-manifest.json'),'qualification_sha256':sha(OUT/'qualification.json'),'proposal_sha256':sha(proposal)}))
