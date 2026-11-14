from pathlib import Path
import hashlib,json,xml.etree.ElementTree as E
R=Path(__file__).resolve().parent;D=R/'draft';OUT=R/'public';OUT.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def write(p,v):p.write_bytes((json.dumps(v,indent=2,ensure_ascii=False)+'\n').encode())
p=read(D/'m1-codex-campaign-proposal-v12.json');final=read(R/'final-entry-gates/result.json')
assert p['execution_bundle']['status']=='FROZEN_QUALIFIED' and not p['execution_authorized']
assert final['exit_code']==0 and final['inputs_unchanged'] and final['proposal_sha256']==sha(D/'m1-codex-campaign-proposal-v12.json')
assert final['campaign_root_absent'] and final['installation_unreserved']
assert read(R/'final-entry-gates/actual-input-verification.json')['status']=='PASS'
groups={};unique=set();external={};inputs=read(D/'offline-finalization.json')['groups']
for name,entry in inputs.items():
 xml=Path(entry['xml']);assert sha(xml)==entry['xml_sha256'];cases=E.parse(xml).getroot().findall('.//testcase')
 assert all(not any(c.find(tag) is not None for tag in ('failure','error','skipped')) for c in cases)
 identities={(c.attrib['classname'],c.attrib['name']) for c in cases};assert len(identities)==len(cases);unique.update(identities)
 relative=xml.relative_to(R).as_posix() if xml.is_relative_to(R) else 'component-evidence/'+name+'/results.xml'
 groups[name]={'tests':len(cases),'failures':0,'errors':0,'skipped':0,'xml_sha256':sha(xml),'artifact':relative,'scope':entry.get('scope')}
 if not xml.is_relative_to(R):external[relative]=xml
selected=set(R.glob('*.py'))|set(D.glob('*.py'))|set(D.glob('*.json'))
selected.update((D/'controller').glob('*.py'));selected.update((D/'protected-transfer').glob('*.py'));selected.update((D/'diffs').glob('*.diff'))
selected.update(x for x in (D/'preparation-history').rglob('*') if x.is_file())
for name in ('timed_install.py','prepare_dependencies.py','probe_direct_interpreter.py','test_timed_install.py','products-requirements.txt','dependency-manifest.json','dependency-preparation.json','direct-interpreter-final.json'):
 selected.add(D/'installation'/name)
for group in ('affected-composition','affected-composition-final','final-origins','final-entry-gates'):
 for name in ('result.json','results.xml','stdout.txt','stderr.txt','module-origins.json','actual-input-verification.json'):
  source=R/group/name
  if source.exists():selected.add(source)
for f in sorted(selected):
 assert f.is_relative_to(R) and not any(x in f.parts for x in ('venv','campaign','pytest-tmp'))
for key,pin in p['execution_bundle']['files'].items():
 if key.startswith('root_driver_'):
  f=Path(pin['path']);assert sha(f)==pin['sha256'];external['root-drivers/'+f.name]=f
driver_dir=Path(p['execution_bundle']['files']['root_driver_common']['path']).parent
for f in [*driver_dir.glob('test*.py'),*driver_dir.glob('*.json'),driver_dir/'README.md']:
 if f.exists():external['root-drivers/'+f.name]=f
source=Path(p['controller_preparation']['source_freeze']['path']).parent
for name in ('runtime-freeze.json','qualification.json','module-origins.json'):
 f=source/name
 if f.exists():external['component-evidence/setup-discovery/'+name]=f
# Explicit predecessor evidence retains timings and avoids promoting old failures.
old=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-read250-candidate-q537zfyi/qualification')
for name in ('runtime-freeze.json','qualification.json','final.xml','predecessor-cli-final.xml','predecessor-timing-failures.json'):
 f=old/name
 if f.exists():external['historical/read250/'+name]=f
records=[]
for relative,f in [(x.relative_to(R).as_posix(),x) for x in sorted(selected)]+sorted(external.items()):
 target=OUT/relative;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();h=sha(f);target.write_bytes(f.read_bytes());assert sha(target)==sha(f)==h
 records.append({'path':relative,'source_sha256':h,'artifact_sha256':h,'bytes':target.stat().st_size})
qualification={'status':'OFFLINE_V12_QUALIFIED_STANDING_AUTHORIZATION_TECHNICAL_BINDING_PENDING',
 'proposal_sha256':sha(D/'m1-codex-campaign-proposal-v12.json'),'groups':groups,'unique_test_cases':len(unique),
 'counting':'Overlapping retained source cases and affected composition cases are deduplicated by classname/name; historical64 and earlier attempts are not added.',
 'history':'V11 closed with one unsettled setup reservation retained. Earlier timing failures and collection error are preserved; no historical failure relabeled.',
 'source_freeze':p['controller_preparation']['source_freeze'],'policy':p['controller_preparation']['policy'],'policy_delta':p['policy_delta'],'ancestry':p['controller_preparation']['ancestry'],
 'scope_qualification':p['scope_qualification'],'product_build_scope':p['package_pins']['build_scope'],
 'runtime_pin_count':len(p['execution_bundle']['files']),'product_payload_count':983,'all_package_pins':984,
 'dependency_files':read(D/'installation/dependency-preparation.json')['dependency_files'],
 'lf_requirements_sha256':sha(D/'installation/products-requirements.txt'),
 'campaign_directory_created':False,'products_installed':False,'technical_v12_binding_created':False,
 'standing_user_authorization_received':True,'new_human_approval_of_hash_required':False,
 'provider_calls':0,'service_actions':0,'credentials_read':0,'m1_complete':False,
 'publication':'Allowlisted offline metadata/source/fixtures only. No environment, product binaries/wheels, private live DB/vault, credentials or synthetic approval directories.'}
write(OUT/'qualification.json',qualification);h=sha(OUT/'qualification.json');records.append({'path':'qualification.json','source_sha256':h,'artifact_sha256':h,'bytes':(OUT/'qualification.json').stat().st_size})
write(OUT/'artifact-manifest.json',{'schema':'m1.public-artifact-manifest','revision':1,'artifacts':records})
print(json.dumps({'public':str(OUT),'artifacts':len(records),'unique_tests':len(unique),'manifest_sha256':sha(OUT/'artifact-manifest.json'),'qualification_sha256':sha(OUT/'qualification.json'),'proposal_sha256':sha(D/'m1-codex-campaign-proposal-v12.json')}))
