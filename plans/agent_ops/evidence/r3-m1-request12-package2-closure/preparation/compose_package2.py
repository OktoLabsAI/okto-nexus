"""Bind the new package to unchanged finite work authority and technical predecessor."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;OLD=HERE.with_name('work-request12')
sys.path.insert(0,str(HERE))
from request_context import current_commands,verify_technical_predecessor
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
old=read(OLD/'amendment.json');assert sha(OLD/'amendment.json')=='249c52325655e2d6c7030e8fe37c1eb6d43726e06954db544970446800da0117'
installed=read(HERE/'package/installation.json');probe=read(HERE/'probe-qualification.json')
assert probe['status']=='CANONICAL_PROBE60_PASS' and probe['installation_sha256']==sha(HERE/'package/installation.json')
assert sha(old['migration']['source_context']['path'])==old['migration']['source_context']['sha256']
assert verify_technical_predecessor(pin(HERE/'technical-predecessor.json'))
sources={key:pin(HERE/Path(entry['path']).relative_to(OLD)) for key,entry in old['sources'].items()}
proposal=read(old['original']['proposal'])
commands=current_commands(read(proposal['execution_bundle']['commands']['path']),installed['python'])
save(HERE/'commands.json',commands)
value=deepcopy(old)
value.update(work_root=str(HERE),sources=sources,commands=pin(HERE/'commands.json'),
    installation=pin(HERE/'package/installation.json'),wheels=installed['wheels'],
    technical_predecessor=pin(HERE/'technical-predecessor.json'),
    installed_probe=pin(HERE/'probe-qualification.json'),native_decision_path=str(HERE/'private/native-decision.json'))
value['basis']['technical_predecessor']=pin(HERE/'technical-predecessor.json')
value['basis']['historical_grants']=pin(HERE/'historical-grants.json')
value['migration']['target_python']=installed['python']
value['bundle_overrides']={key:pin(HERE/Path(entry['path']).relative_to(OLD)) for key,entry in old['bundle_overrides'].items()}
value['technical_supersession']={'predecessor_amendment':pin(OLD/'amendment.json'),'predecessor_freeze':pin(OLD/'runtime-freeze.json'),
    'original_upgrade_returncode':2,'original_code':'UPGRADE_ENVIRONMENT_UNAVAILABLE',
    'new_candidate_requires_new_upgrade_plan':True,'old_plan_reused':False,'reservation_refunded':False,
    'historical_stream_settlement_synthesized':False,'source_commits':read(HERE/'package/build-provenance.json')['sources'],
    'changed_controller_module':'fresh_work_controller.py path fence only; other14bytes unchanged',
    'qualification_reuse':'Original20 composition+10upgrade+10controller+6wrapper suites retained; only new path/technical-predecessor5cases, installed payload/prefix and canonical probe60 qualified anew.'}
save(HERE/'amendment.json',value)
print(json.dumps({'amendment_sha256':sha(HERE/'amendment.json'),'source_files':len(sources),'new_ids':value['request_ids'],
    'policy':value['policy'],'technical_predecessor_sha256':value['technical_predecessor']['sha256']}))
