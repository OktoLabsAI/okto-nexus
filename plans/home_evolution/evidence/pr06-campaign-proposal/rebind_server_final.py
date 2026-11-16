"""Rebind only the qualified package, preserving the existing inert namespace."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

BASE=Path('C:/Users/jpamb/AppData/Local/Temp/home-r1-local-driver-6t4xonw6')
ANCESTOR_SHA='cbb2a45ba9cc99833b5af881abc8415c4c7d355c436d6e05e8cfab4288fdd6af'
FIRST_SHA='5a8c72d04e9e4adc426173dd14971ef28c6dec599af2bfea42b5deaf61012c40'
WHEEL=Path('C:/Users/jpamb/AppData/Local/Temp/home-r1-package-server-final-el33h4ik/dist/okto_nexus-0.3.4-py3-none-any.whl')
WHEEL_SHA='c1c45e2a3dc8b9f0bed348ddc2d09ab4d0afccbaae2b8c19253fdcaf4980b759'
QUAL=Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/home_evolution/evidence/pr10-package-server-final/qualification.json')
QUAL_SHA='629985a6e8d40149f6d89e47f0633afdbc6e133f9886a0d8195a9a7ab6c18b42'


def main():
    spec=importlib.util.spec_from_file_location('inert_binding',BASE/'bind_plan.py')
    binding=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(binding)
    require,sha,publish=binding.require,binding.sha,binding.publish
    ancestor=BASE/'candidate-final-ui.json';first=BASE/'candidate.json'
    require(sha(ancestor)==ANCESTOR_SHA and sha(first)==FIRST_SHA,'ANCESTOR_CHANGED')
    old=json.loads(ancestor.read_text(encoding='utf-8'))
    root=Path(old['campaign_root'])
    require(not root.exists(),'CAMPAIGN_ALREADY_STARTED_RECONCILE_REQUIRED')
    require(not list(BASE.glob('*authorization*')),'AUTHORIZATION_PRESENT_RECONCILE_REQUIRED')
    require(not (BASE/'candidate-server-final.json').exists(),'FINAL_CANDIDATE_EXISTS_RECONCILE_REQUIRED')
    require(not any(Path(old['scope_paths']['private']).glob('*reserved*')),'RESERVATION_PRESENT_RECONCILE_REQUIRED')
    require(old['policy']==binding.POLICY,'POLICY_CHANGED')
    require(all(sha(p['path'])==p['sha256'] for p in old['pins']),'ORIGINAL_RUNTIME_CODE_CHANGED')
    require(sha(old['codex_executable'])==old['codex_content_fingerprint'],'NATIVE_EXECUTABLE_CHANGED')
    # Technical parameter only, in this process; original binder/driver bytes
    # and their original runtime pins are never modified. make_candidate is not called.
    binding.FINAL_WHEEL_SHA=WHEEL_SHA
    snapshot=binding.package_snapshot(WHEEL,QUAL,QUAL_SHA)
    require(snapshot['python']==old['python'] and snapshot['python_images']==old['python_images'],'PYTHON_IMAGES_CHANGED')
    new=copy.deepcopy(old)
    new['package']=snapshot['package']
    new['technical_rebind']={'ancestor_candidate_sha256':ANCESTOR_SHA,
        'ancestor_chain_sha256':[FIRST_SHA,ANCESTOR_SHA],
        'source_commit':'3d95aad8c1b5d2e6354cd872512586fd7a02aec9',
        'reason':'Qualified A08 Server-attention package, same inert campaign before any consent or effect.',
        'helper_sha256':sha(__file__),'authorization_inherited':False,'budget_reset':False,
        'no_reservations_present':True}
    changed=sorted(k for k in set(new)|set(old) if new.get(k)!=old.get(k))
    require(changed==['package','technical_rebind'],'NON_PACKAGE_SCOPE_CHANGED')
    for key in old:
        if key not in changed:require(new[key]==old[key],'IMMUTABLE_SCOPE_CHANGED')
    publish(BASE/'candidate-server-final.json',new)
    require(sha(ancestor)==ANCESTOR_SHA and sha(first)==FIRST_SHA,'ANCESTOR_CHANGED_DURING_REBIND')
    require(not root.exists() and not list(BASE.glob('*authorization*')),'RUNTIME_EFFECT_OR_AUTHORIZATION_CREATED')
    result={'status':'INERT_SERVER_FINAL_REBIND_COMPLETE','ancestor_candidate_sha256':ANCESTOR_SHA,
        'ancestor_chain_sha256':[FIRST_SHA,ANCESTOR_SHA],
        'candidate_sha256':sha(BASE/'candidate-server-final.json'),'changed_top_level_keys':changed,
        'immutable_scope_equal':True,'python_images_equal':True,'original_runtime_pins_equal':True,
        'driver_sha256':sha(BASE/'driver.py'),'installed_payload_count':len(new['package']['payload_pins']),
        'wheel_sha256':WHEEL_SHA,'qualification_sha256':QUAL_SHA,
        'campaign_root_exists':False,'authorization_exists':False,'reservations':0,
        'service_actions':0,'provider_calls':0,'native_executable_executions':0,
        'native_executable_bytes_verified':True,
        'binding_function':'Existing qualified package_snapshot; fixed wheel constant changed only in helper process memory, original source files unchanged.'}
    publish(BASE/'rebind-server-result.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
