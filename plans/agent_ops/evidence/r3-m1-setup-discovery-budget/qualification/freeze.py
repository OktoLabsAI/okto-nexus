"""Freeze source/evidence only; never copy fixture databases or private inputs."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
Q=Path(__file__).resolve().parent;ROOT=Q.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((Q/'predecessor-runtime-freeze.json').read_text())
assert sha(Q/'predecessor-runtime-freeze.json')=='d22afc44b0776b3f34429c59d311c85c53d19f7d15ab5d5d7a96135947d333f0'
runtime=[{'path':item['path'],'sha256':sha(ROOT/item['path'])} for item in old['runtime']]
changed=[a['path'] for a,b in zip(runtime,old['runtime']) if a['sha256']!=b['sha256']]
assert changed==['controller/setup_journal.py']
cases=list(ET.parse(Q/'final.xml').iter('testcase'))
assert len(cases)==73 and not any(c.find('failure') is not None or c.find('error') is not None or c.find('skipped') is not None for c in cases)
before=json.loads((Q/'final-run-sources.json').read_text())
assert all(sha(ROOT/name)==value for name,value in before.items())
testpaths=sorted((ROOT/'controller').glob('test_*.py'))
tests=[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in testpaths]
qual={'classification':'OFFLINE_SETUP_DISCOVERY_BUDGET_FIX_QUALIFIED_NOT_M1_EXECUTION',
    'cases_passed':73,'deselected':1,'retained_fixture_cases':63,'new_deterministic_cases':10,
    'excluded_test':'test_real_closed_v10_full_schema_prepares_once_and_stays_readonly',
    'exclusion_reason':'Historical private database outside current offline fixture scope; no new access needed.',
    'final_suite_runs':1,'final_xml_sha256':sha(Q/'final.xml'),
    'module_origins_sha256':sha(Q/'module-origins.json'),
    'diagnosis_sha256':sha(Q/'v11-diagnosis-final.json'),
    'predecessor_freeze_sha256':sha(Q/'predecessor-runtime-freeze.json'),
    'changed_runtime_files':changed,'schema_ms':250,'snapshot_ms':250,'aggregate_ms':600,'freshness_ms':1000,'deadline_seconds':120,
    'runner_command':'rtk proxy C:/Users/jpamb/AppData/Local/Temp/m1-v11-bundle-racan37z/draft/installation/venv/Scripts/python.exe -I -B '+str(Q/'run_final.py'),
    'runner_cwd':'D:/Projetos/Techridy/okto_labs_okto_nexus',
    'runner_scope':'Pinned installed v11 prefix; isolated Python; explicit candidate source path; plugin autoload disabled.',
    'ruff_selected_checks':'E9,F63,F7,F82','compile_only_passed':True,
    'campaign_or_receipt_created':False,'model_or_service_executed':False,
    'existing_checkpoint_or_accounting_changed':False,'private_inputs_copied':False,
    'runtime':runtime,'tests':tests}
with (Q/'qualification.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(qual,f,indent=2);f.write('\n')
freeze={'classification':qual['classification'],'runtime':runtime,'tests':tests,
    'qualification_sha256':sha(Q/'qualification.json'),'predecessor_freeze_sha256':qual['predecessor_freeze_sha256']}
with (Q/'runtime-freeze.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(freeze,f,indent=2);f.write('\n')
allow=[ROOT/item['path'] for item in runtime+tests]+[ROOT/'CHANGELOG.md']
allow += [Q/name for name in ['run_final.py','collect_diagnostic.py','freeze.py','predecessor-runtime-freeze.json',
    'final-run-sources.json','module-origins.json','final.xml','v11-diagnosis.json','v11-diagnosis-final.json','qualification.json','runtime-freeze.json']]
manifest={'classification':'PUBLIC_SOURCE_AND_SANITIZED_EVIDENCE_ONLY',
    'excluded':['qualification/final-tmp/**','__pycache__/**','private database/auth/transcript/receipt inputs'],
    'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in allow]}
with (Q/'public-allowlist.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(manifest,f,indent=2);f.write('\n')
print(json.dumps({name:sha(Q/name) for name in ['runtime-freeze.json','qualification.json','public-allowlist.json','v11-diagnosis-final.json']}))
