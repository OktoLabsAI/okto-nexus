"""Freeze qualified package2; no lifecycle or runtime dispatch."""
from pathlib import Path
import hashlib,json,ast
H=Path(__file__).resolve().parent;OLD=H.with_name('work-request12')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
A=read(H/'amendment.json');digest=sha(H/'amendment.json');installed=read(H/'package/installation.json')
assert read(H/'gate-qualification.json')['amendment_sha256']==digest
assert read(H/'probe-qualification.json')['status']=='CANONICAL_PROBE60_PASS'
for entry in A['sources'].values():assert sha(entry['path'])==entry['sha256'];ast.parse(Path(entry['path']).read_text(encoding='utf-8-sig'))
workflow=read(OLD/'workflow.json')
for step in workflow['steps']:
    step['argv']=[arg.replace(str(OLD),str(H)) for arg in step['argv']]
    index=step['argv'].index('--expected-amendment-sha256')+1;step['argv'][index]=digest
workflow['amendment_sha256']=digest;save(H/'workflow.json',workflow)
ancestry=read(H/'source-ancestry.json')
for value in ancestry['sources'].values():
    value['current']=pin(value['path']);value['byte_equal']=value['current']['sha256']==value['ancestor']['sha256']
ancestry['status']='QUALIFIED_PACKAGE2_ONLY_TWO_SOURCE_DELTAS'
assert {k for k,v in ancestry['sources'].items() if not v['byte_equal']}=={'context','fresh_work_controller'}
save(H/'source-ancestry.json',ancestry)
qualification={'status':'OFFLINE_PACKAGE2_QUALIFIED_NO_RUNTIME_EXECUTION',
    'amendment_sha256':digest,'installation':pin(H/'package/installation.json'),
    'build':pin(H/'package/build-provenance.json'),'probe60':pin(H/'probe-qualification.json'),
    'composed_gate':pin(H/'gate-qualification.json'),
    'delta_tests':{'passed':5,'xml':pin(H/'path-delta.xml'),'source':pin(H/'test_package2_delta.py'),
        'runner':str(OLD/'package/venv/Scripts/python.exe'),'flags':['-I','-B','-X','utf8'],
        'scope':'Real constructor path fence, unchanged policy/14modules, exact technical predecessor and no-refund negative fixtures.'},
    'reused_qualification':{'source':pin(OLD/'qualification.json'),'composition':20,'upgrade':10,'controller':10,'wrappers':6,
        'not_rerun':True,'ancestry':pin(H/'source-ancestry.json')},
    'technical_predecessor':pin(H/'technical-predecessor.json'),
    'carry_tokens':272648,'carry_reservations':11,'new_model_reservations':0,
    'services_started':0,'provider_calls':0,'upgrade_actions':0,'acceptance_promoted':False,'remote_DX40':'PENDING'}
save(H/'qualification.json',qualification)
status=read(H/'preparation-status.json')
status.update(status='OFFLINE_QUALIFIED_NOT_EXECUTED',executable_manifest_exists=True,package_installed=True,
    canonical_probe60='PASS',root_execution_review_required=True,
    previous_preparation_status='WAITING_STREAMING_FIX_COMMITS_AND_WHEELS')
save(H/'preparation-status.json',status)
paths=[H/name for name in ('amendment.json','commands.json','workflow.json','qualification.json','README.md',
    'technical-predecessor.json','source-ancestry.json','historical-grants.json','preparation-status.json',
    'test_package2_delta.py','path-delta.xml','build_packages.py','probe_new_package.py','probe-qualification.json',
    'compose_package2.py','check_composed_gate.py','gate-qualification.json','freeze_package2.py',
    'package/build-provenance.json','package/installation.json','package/dependency-manifest.json',
    'package/install_packages.py','package/prepare_dependencies.py')]
paths += [Path(v['path']) for v in A['sources'].values()]
assert not (H/'public').exists() and not (H/'private').exists()
manifest={'status':'FROZEN_OFFLINE_QUALIFIED_ROOT_REVIEW_REQUIRED','amendment_sha256':digest,
    'files':{str(p.relative_to(H)).replace('\\','/'):pin(p) for p in paths},'no_runtime_effects':True,
    'technical_supersession_not_new_campaign':True}
save(H/'runtime-freeze.json',manifest)
save(H/'public-allowlist.json',{'files':[*manifest['files'].values(),pin(H/'runtime-freeze.json')],
    'excluded':['private','runtime-private','venv','wheels','source archives','auth','transcripts','ownership token/nonce']})
print(json.dumps({'amendment_sha256':digest,'freeze_sha256':sha(H/'runtime-freeze.json'),
    'qualification_sha256':sha(H/'qualification.json'),'allowlist_sha256':sha(H/'public-allowlist.json'),'files':len(manifest['files'])}))
