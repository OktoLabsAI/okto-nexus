"""Publish offline qualification and finite commands after all sources are stable."""
from pathlib import Path
import hashlib,json,shutil,ast
H=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
A=read(H/'amendment.json');digest=sha(H/'amendment.json');python=read(H/'package/installation.json')['python']
for entry in A['sources'].values():
    assert sha(entry['path'])==entry['sha256']
    ast.parse(Path(entry['path']).read_text(encoding='utf-8-sig'))
base=[python,'-X','utf8','-I','-B']
args=['--amendment',str(H/'amendment.json'),'--expected-amendment-sha256',digest]
workflow=[]
for label,script,selection in [
    ('prepare','request_entry.py',['prepare']),('upgrade-plan','invoke_request.py',['upgrade','plan']),
    ('upgrade-apply','invoke_request.py',['upgrade','apply']),
    ('install','invoke_request.py',['lifecycle','nexus','install']),('start','invoke_request.py',['lifecycle','nexus','start']),
    ('watch','request_entry.py',['observation','nexus','watch']),
    ('authorization-review','invoke_request.py',['authorize_local','review']),
    ('authorization-apply','invoke_request.py',['authorize_local','apply']),
    ('useful12','invoke_request.py',['work','local','useful']),
    ('continuation13','invoke_request.py',['work','local','continuation']),
    ('normal-stop','invoke_request.py',['lifecycle','nexus','stop']),
    ('cleanup-proof','request_entry.py',['cleanup','nexus']),
    ('uninstall','invoke_request.py',['lifecycle','nexus','uninstall']),
    ('final-presence','request_entry.py',['final_presence']),('closure','request_entry.py',['close'])]:
    workflow.append({'label':label,'argv':base+[str(H/script),*args,*selection],
        'background_retained_observer':label=='watch','conditional':label in ('authorization-apply','continuation13','normal-stop')})
write(H/'workflow.json',{'amendment_sha256':digest,'steps':workflow,'shell':False,
    'scope':'Root executes serial selections; watcher runs concurrently. Commands are not executed by this artifact.'})
evidence=H/'offline-evidence';evidence.mkdir(exist_ok=True)
origins=[Path('C:/Users/jpamb/AppData/Local/Temp/m1_request12_upgrade_root_qualification.json'),
    Path('C:/Users/jpamb/AppData/Local/Temp/m1_request12_upgrade_review_tests.py'),
    Path('C:/Users/jpamb/AppData/Local/Temp/m1-request12-controller-875t5rwb/wrapper-qualification.json'),
    Path('C:/Users/jpamb/AppData/Local/Temp/m1-request12-controller-875t5rwb/test_wrapper_delta.py'),
    Path('C:/Users/jpamb/AppData/Local/Temp/m1-request12-controller-875t5rwb/qualification.json'),
    Path('C:/Users/jpamb/AppData/Local/Temp/m1-request12-controller-875t5rwb/runtime-freeze.json')]
copied={}
for i,p in enumerate(origins):
    target=evidence/(str(i)+'-'+p.name)
    if not target.exists():shutil.copyfile(p,target)
    assert sha(p)==sha(target);copied[str(p)]=pin(target)
qualification={'status':'OFFLINE_QUALIFIED_NOT_EXECUTED','new_package':A['installation'],
    'amendment_sha256':digest,'own_tests':{'passed':20,'initial_passed':18,
        'initial_xml':pin(H/'qualification-initial.xml'),'final_xml':pin(H/'qualification-final.xml'),
        'command':[python,'-I','-B','-X','utf8','-m','pytest','-q',str(H/'test_preparation.py'),
            '--junitxml='+str(H/'qualification-final.xml')],
        'environment':'Own installed venv; -I/-B/-Xutf8; no editable/PYTHONPATH. Fixtures only, no live service or DB.'},
    'independent_qualifications':{'root_upgrade_tests':10,'controller_tests':10,'wrapper_delta_tests':6},
    'copied_qualification_sources':copied,'syntax_sources':len(A['sources']),
    'product_source_or_wheel_mutated':False,'services_started':0,'models_called':0,'grants_issued':0,
    'runtime_evidence_directories_created':False,'historical_original_unsettled_preserved':True,
    'acceptance_promoted':False,'remote_DX40':'PENDING'}
write(H/'qualification.json',qualification)
paths=[H/'amendment.json',H/'commands.json',H/'workflow.json',H/'qualification.json',H/'README.md',
    H/'test_preparation.py',H/'qualification-initial.xml',H/'qualification-final.xml',
    H/'compose.py',H/'freeze_preparation.py',H/'package/installation.json',H/'package/install_packages.py',
    H/'package/prepare_dependencies.py',H/'package/dependency-manifest.json',H/'historical-grants.json',
    *[Path(v['path']) for v in A['sources'].values()],*[Path(v['path']) for v in copied.values()]]
assert not (H/'public').exists() and not (H/'private').exists()
manifest={'status':'FROZEN_OFFLINE_QUALIFIED_ROOT_REVIEW_REQUIRED','amendment_sha256':digest,
    'files':{str(p.relative_to(H)).replace('\\','/'):pin(p) for p in paths},
    'no_real_effects':True,'authority':'Standing authorization; technical source binding only.'}
write(H/'runtime-freeze.json',manifest)
write(H/'public-allowlist.json',{'files':[*manifest['files'].values(),pin(H/'runtime-freeze.json')],
    'excluded':['private','runtime-private','venv','wheels','auth','provider transcripts','native argv/nonce/token']})
print(json.dumps({'amendment_sha256':digest,'freeze_sha256':sha(H/'runtime-freeze.json'),
    'qualification_sha256':sha(H/'qualification.json'),'allowlist_sha256':sha(H/'public-allowlist.json'),
    'files':len(manifest['files']),'actual_effects':0}))
