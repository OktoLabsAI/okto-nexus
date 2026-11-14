from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent
B=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/successor14/work-request12-package2')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
assert sha(B/'runtime-freeze.json')=='9706592bce4b58cf7b95bcf5fb60e682c28f1542c12b68f731a7e9f501e8e96b'
original=(B/'local_work.py').read_bytes();needle=b'from controller import POLICY'
assert original.count(needle)==1
overlay=original.replace(needle,b'from legacy_controller import POLICY')
(H/'local_work.py').write_bytes(overlay)
cp=read(B/'private/controller.json')
assert cp['requests']=={} and cp['collector']['state']['requests']=={} and cp['faults']==[]
assert not any(p.name.startswith('m1v14-local-work-12-') for p in (B/'public').iterdir())
manifest={'format':'okto.m1.policy_import_overlay.v1','root':str(H),'maximum_useful_reentries':1,
    'new_model_ids':['m1v14-local-work-12','m1v14-local-work-13'],
    'sources':{name:pin(H/name) for name in ('entry.py','invoke.py','close_companion.py','local_work.py')},
    'basis':{'amendment':pin(B/'amendment.json'),'freeze':pin(B/'runtime-freeze.json'),
        'original_work':pin(B/'local_work.py'),'original_facade':pin(B/'modules/controller.py'),
        'current_legacy':pin(B/'modules/legacy_controller.py'),
        'failed_wrapper':pin(B/'runtime-private/work-local-useful.returned.json'),
        'failed_stderr':pin(B/'runtime-private/work-local-useful.stderr')},
    'initial_checkpoint_sha256':sha(B/'private/controller.json'),
    'delta':'Exactly one import line: from controller import POLICY -> from legacy_controller import POLICY. Entry requires exact amendment policy equality.',
    'unchanged':['Context','controller modules','private checkpoint','package wheels','grant','service','original invocation ledger'],
    'model_reservation_created_by_preparation':False,'original_failure_reclassified':False,
    'future_force_authorized':False,'execution_status':'PREPARED_ROOT_REVIEW_REQUIRED'}
manifest['sources']['work_overlay']=manifest['sources'].pop('local_work.py')
write(H/'manifest.json',manifest)
print(json.dumps({'manifest_sha256':sha(H/'manifest.json'),'work_overlay_sha256':sha(H/'local_work.py'),
    'initial_checkpoint_sha256':manifest['initial_checkpoint_sha256']}))
