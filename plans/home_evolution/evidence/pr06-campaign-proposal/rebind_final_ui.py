"""Prepare an inert candidate, then bind ONLY an actual consent receipt to its hash.
No CLI product handlers, services, native process or user config/auth reads here.
"""
from pathlib import Path
import argparse
import base64
from importlib import metadata, import_module
import json
import sys
import uuid
import zipfile
sys.path.insert(0,str(Path(__file__).parent))
from driver import sha, publish, POLICY, consent_valid
from usage import require, owned

FINAL_WHEEL_SHA='7e1563622f4becb21cc62b6182cb4683c7546861256c355c16bb9aa78efa87ff'


def package_snapshot(wheel, qualification, qualification_sha):
    require(sha(wheel)==FINAL_WHEEL_SHA,'FINAL_WHEEL_CHANGED')
    require(sha(qualification)==qualification_sha,'PACKAGE_QUALIFICATION_CHANGED')
    tested=json.loads((Path(__file__).parent/'parser-origins.json').read_text())
    for item in tested['origins']:
        module=import_module(item['module']) # import only; no CLI handler call.
        require(sha(module.__file__)==item['sha256'],'PARSER_CHANGED_REQUALIFY_FOCAL_ONLY')
    prefix=Path(sys.prefix).resolve(); payload=[];versions={}
    for name,expected in [('okto-nexus','0.3.4'),('okto-nexus-connector-core','0.0.14')]:
        dist=metadata.distribution(name);require(dist.version==expected,'PACKAGE_VERSION_CHANGED')
        versions[name]=dist.version
        for entry in dist.files or []:
            if entry.suffix=='.pyc' or entry.hash is None:continue
            target=Path(dist.locate_file(entry)).resolve()
            require(target.is_relative_to(prefix),'INSTALLED_ORIGIN_OUTSIDE_PREFIX')
            digest=sha(target)
            require(entry.hash.mode=='sha256' and base64.urlsafe_b64encode(bytes.fromhex(digest)).decode().rstrip('=')==entry.hash.value,
                    'INSTALLED_RECORD_MISMATCH')
            payload.append({'path':str(target),'sha256':digest})
    # Check actual Nexus wheel payload bytes against this prefix, not just RECORD.
    dist=metadata.distribution('okto-nexus')
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.startswith('okto_nexus/'):continue
            target=Path(dist.locate_file(entry.filename)).resolve()
            require(target.is_relative_to(prefix) and target.read_bytes()==archive.read(entry),'FINAL_WHEEL_PAYLOAD_CHANGED')
    require(len(payload)>100,'PAYLOAD_REQUIRED')
    images={}
    for image in {Path(sys.executable),Path(sys.executable).with_name('pythonw.exe'),
                  Path(sys._base_executable),Path(sys._base_executable).with_name('pythonw.exe')}:
        require(image.is_file(),'PYTHON_IMAGE_MISSING');images[str(image.resolve())]=sha(image)
    return {'python':{'path':str(Path(sys.executable).resolve()),'sha256':sha(sys.executable)},
            'python_images':images,'package':{'installed_payloads_verified':True,'payload_pins':payload,
             'versions':versions,'wheel':{'path':str(Path(wheel).resolve()),'sha256':FINAL_WHEEL_SHA},
             'qualification_path':str(Path(qualification).resolve()),'qualification_sha256':qualification_sha}}



def rebind():
    base=Path(__file__).parent
    ancestor=base/'candidate.json'
    ancestor_sha='5a8c72d04e9e4adc426173dd14971ef28c6dec599af2bfea42b5deaf61012c40'
    require(sha(ancestor)==ancestor_sha,'ANCESTOR_CHANGED')
    old=json.loads(ancestor.read_text(encoding='utf-8'))
    require(not Path(old['campaign_root']).exists(),'CAMPAIGN_ALREADY_STARTED')
    require(not (base/'actual-authorization.json').exists(),'AUTHORIZATION_ALREADY_EXISTS')
    require(all(sha(p['path'])==p['sha256'] for p in old['pins']),'ORIGINAL_RUNTIME_CHANGED')
    require(old['policy']==POLICY,'POLICY_CHANGED')
    package=package_snapshot(
      'C:/Users/jpamb/AppData/Local/Temp/home-r1-package-ui-final-svjjgq53/dist/okto_nexus-0.3.4-py3-none-any.whl',
      'D:/Projetos/Techridy/okto_labs_okto_nexus/plans/home_evolution/evidence/pr06-package-ui-final/qualification.json',
      '9a2a20e26682b4ac6416a1f62a7c07bea499bef50d22c1137188bc2a96b4d58a')
    new={**old,**package,'technical_rebind':{
      'ancestor_candidate_sha256':ancestor_sha,'source_commit':'fa2e4215e47db25ed884c7fe001bfedb0cd9fcb3',
      'reason':'Final qualified UI wheel, same campaign before any consent or effect.',
      'helper_sha256':sha(__file__),'authorization_inherited':False,'budget_reset':False}}
    changed=sorted(k for k in set(new)|set(old) if new.get(k)!=old.get(k))
    require(set(changed)<= {'python','python_images','package','technical_rebind'},'SCOPE_CHANGED')
    for key in ('campaign_id','campaign_root','port','scope_paths','request_ids','policy','pins','codex_root','codex_executable','codex_content_fingerprint','codex_candidate_ref','provider_home','effects'):
      require(new[key]==old[key],'IMMUTABLE_SCOPE_CHANGED')
    publish(base/'candidate-final-ui.json',new)
    require(sha(ancestor)==ancestor_sha and not Path(new['campaign_root']).exists(),'ANCESTOR_OR_RUNTIME_CHANGED')
    result={'status':'INERT_FINAL_UI_REBIND_COMPLETE','ancestor_sha256':ancestor_sha,
      'candidate_sha256':sha(base/'candidate-final-ui.json'),'changed_top_level_keys':changed,
      'immutable_scope_equal':True,'original_runtime_pins_equal':True,'installed_payload_count':len(package['package']['payload_pins']),
      'campaign_root_exists':False,'authorization_exists':False,'service_actions':0,'provider_calls':0,
      'package_snapshot_function':'Same read-only function as qualified bind_plan.py; only fixed FINAL_WHEEL_SHA updated in this separate helper. No original source modified.'}
    publish(base/'rebind-result.json',result)
    print(json.dumps(result))

if __name__=='__main__':rebind()
