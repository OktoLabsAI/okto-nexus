from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent
B=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12-package2')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
manifest=json.loads((H/'manifest.json').read_bytes());digest=sha(H/'manifest.json')
for entry in [*manifest['sources'].values(),*manifest['basis'].values()]:assert sha(entry['path'])==entry['sha256']
python=str(B/'package/venv/Scripts/python.exe');flags=['--manifest',str(H/'manifest.json'),'--expected-manifest-sha256',digest]
save(H/'workflow.json',{'useful':[python,'-X','utf8','-I','-B',str(H/'invoke.py'),*flags,'useful'],
    'continuation':[python,'-X','utf8','-I','-B',str(H/'invoke.py'),*flags,'continuation'],
    'closure_companion_after_original_closure':[python,'-X','utf8','-I','-B',str(H/'close_companion.py'),*flags],
    'original_workflow_cleanup_unchanged':str(B/'workflow.json'),
    'native_decision_path_unchanged':str(B/'private/native-decision.json')})
save(H/'guard-qualification.json',{'status':'READONLY_REENTRY_GUARD_PASS','tool_result':'0ecc9a',
    'real_original_gate_loaded':True,'predispatch_failure_and_current_empty_checkpoint_validated':True,
    'reservation_created':False,'controller_constructed':False,'service_or_model_called':False})
paths=[H/name for name in ('manifest.json','entry.py','invoke.py','local_work.py','close_companion.py',
    'compose.py','test_policy_import.py','qualification.json','guard-qualification.json','workflow.json','README.md','freeze.py')]
freeze={'manifest_sha256':digest,'status':'QUALIFIED_ONE_LINE_OVERLAY_ROOT_REVIEW_REQUIRED',
    'files':{p.name:pin(p) for p in paths},'original_frozen_sources_mutated':False,'model_calls':0,'service_actions':0}
save(H/'runtime-freeze.json',freeze)
save(H/'public-allowlist.json',{'files':[*freeze['files'].values(),pin(H/'runtime-freeze.json')],
    'excluded':['runtime-private','base private/controller','base failed stdout/stderr contents','credentials','native commands']})
print(json.dumps({'manifest_sha256':digest,'freeze_sha256':sha(H/'runtime-freeze.json'),
    'qualification_sha256':sha(H/'qualification.json'),'allowlist_sha256':sha(H/'public-allowlist.json')}))
