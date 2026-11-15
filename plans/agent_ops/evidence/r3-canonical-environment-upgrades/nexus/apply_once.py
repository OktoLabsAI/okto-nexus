from pathlib import Path
import hashlib,json,subprocess,sys,traceback,zipfile
HERE=Path(__file__).resolve().parent
PRIVATE=HERE/'private'
Q=Path('C:/Users/jpamb/AppData/Local/Temp/r3-status-fixed-campaign-package-ddwnb5vx')
STATE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign/nexus-home')
PLAN=PRIVATE/'nexus-upgrade-plan.json'
REVISION='5cb3154e06ce592f9d0ff3749575bd26b06116233ca90006ed3f490d59ed6264'
def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(65536),b''): digest.update(chunk)
    return digest.hexdigest()
def save(name,value):
    with (HERE/name).open('x',encoding='utf-8') as stream: json.dump(value,stream,indent=2); stream.write('\n')
def sql_hashes():
    projection=HERE/'projection.json'
    assert sha(projection)=='12bf970be8fb2ae2a68d7d7e0ae64c624a8b81d74e6755d276ab0369e1112bd4'
    baseline=json.loads(projection.read_text())['sql_after']
    assert len(baseline)==30
    values={}
    for name in baseline:
        p=Path(name)
        assert p.resolve().is_relative_to(STATE.resolve()) and not any(word in p.name.lower() for word in ('auth','vault'))
        values[name]={'sha256':sha(p),'bytes':p.stat().st_size}
    return values
assert Path(sys.prefix).resolve()==(Q/'venv').resolve()
assert sha(PLAN)=='98b7a71d86b7d882cca4737d2270a4e894694bef5282c0b3b304f42b6355d961'
assert sha(Q/'installation.json')=='0055c57c33616c12ddfe78c12d1d940423c62f437a7722959976b7baf601b880'
doc=json.loads(PLAN.read_text()); body=doc['plan']; source=body['source_context']; target=body['target_context']
assert doc['plan_revision']==REVISION
allowed={'revision','executable','environment_prefix','package_version','core_version','environment_fingerprint'}
changed={k for k in set(source)|set(target) if source.get(k)!=target.get(k)}
assert changed<=allowed and {k:v for k,v in source.items() if k not in allowed}=={k:v for k,v in target.items() if k not in allowed}
assert Path(target['executable']).resolve()==Path(sys.executable).resolve()
installation=json.loads((Q/'installation.json').read_text()); count=0
for item in installation['wheels']:
    wheel=Q/item['path']; assert sha(wheel)==item['sha256']
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith(('okto_nexus/','okto_nexus_connector/','nexus_connector_core/')) and not name.endswith('/'):
                assert (Q/'venv/Lib/site-packages'/name).read_bytes()==archive.read(name); count+=1
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
from okto_nexus.adapters.outbound.service_manager.upgrade import for_lifecycle
from okto_nexus.service_environment import probe
service=resolve_local_service(['--home',str(STATE)],action='upgrade-apply')
upgrade=for_lifecycle(service.adapter); host=upgrade.host
assert sha(host.context_path)=='b4eaee8c2106f8130fe66d2818e563df709861acb459461310247f1fcab46d43'
restored_manifest=Path('C:/Users/jpamb/AppData/Local/Temp/r3-codex0157-restore-attempt2-60na9ol4/destination-manifest.json')
assert sha(restored_manifest)=='043aef7cb9da43554fa6628471ab84d903dba1598ec4296ec2f2f66363525125'
restored=json.loads(restored_manifest.read_text()); root=Path(restored['target'])
assert len(restored['files'])==48
for relative,digest in restored['files'].items():
    path=root/relative
    assert path.resolve().is_relative_to(root.resolve()) and sha(path)==digest
assert host.digest(body)==REVISION and host.read(host.context_path)==source
assert probe(sys.executable)==body['candidate']
status=host.status(); receipt,task=host.installed()
assert status['state']=='stopped' and status.get('pid') is None
assert receipt==body['source_receipt'] and task and not task.active and task.state!=0
assert task.digest==body['source_native_digest'] and task.xml==body['source_native_xml']
marker=host.optional(host.run_path); shutdown=host.optional(host.shutdown_path)
assert marker['generation']==shutdown['generation']==body['source_generation']=='f8d19439521b499275eee719e97c8e12'
assert marker['instance_id']==body['instance_id']==host.instance_id
assert marker['state']=='drained' and shutdown['state']=='DRAINED'
before=sql_hashes(); context_before=sha(host.context_path)
assert before==json.loads((HERE/'projection.json').read_text())['sql_after']
preflight={'plan_revision':REVISION,'private_plan_sha256':sha(PLAN),'changed_context_fields':sorted(changed),
 'unchanged_other_context_fields':True,'candidate_probe_equal':True,'payloads_equal':count,'restored_discovery_files':48,
 'canonical_state':status['state'],'canonical_pid':status.get('pid'),'native_state':task.state,'native_active':task.active,
 'source_generation':body['source_generation'],'source_native_digest':task.digest,'context_before_sha256':context_before,
 'sql_before':before,'operation':'ONE_CANONICAL_UPGRADE_APPLY_NO_START'}
save('apply-preflight.json',preflight)
# Exclusive durable selection prevents replay even if observation is lost.
save('apply-reserved.json',{'plan_revision':REVISION,'private_plan_sha256':sha(PLAN),'selection_count':1})
args=[sys.executable,'-I','-B','-X','utf8','-m','okto_nexus.adapters.inbound.cli.main','service','upgrade-apply','--home',str(STATE),'--json','--plan-file',str(PLAN),'--expected-revision',REVISION]
result={'plan_revision':REVISION,'effect_selected':True,'retry_performed':False,'start_selected':False,'provider_invoked':False}
try:
    with (PRIVATE/'apply.stdout').open('xb') as out,(PRIVATE/'apply.stderr').open('xb') as err:
        process=subprocess.Popen(['rtk','proxy',*args],stdout=out,stderr=err)
        code=process.wait()
    result['exit_code']=code
    # JSON output remains private; publish only the documented outcome fields.
    output=json.loads((PRIVATE/'apply.stdout').read_text(encoding='utf-8'))
    payload=output.get('data',output) if isinstance(output,dict) else {}
    if isinstance(payload,dict):
        result['cli_projection']={k:payload[k] for k in ('applied','changed','plan_revision','migration_state','target_version') if k in payload}
    current=host.read(host.context_path); after_status=host.status(); after_receipt,after_task=host.installed()
    definition=host.definition(target,body['target_token'])
    shape_equal=bool(after_task and host.matches(body['source_native_xml'],after_task.xml,definition))
    completed=host.optional(host.completed_path)
    after=sql_hashes()
    result.update(context_equals_target=current==target,context_after_sha256=sha(host.context_path),
      target_prefix=current.get('environment_prefix'),canonical_state=after_status['state'],canonical_pid=after_status.get('pid'),
      native_state=after_task.state if after_task else None,native_active=after_task.active if after_task else None,
      native_execution_only_change=shape_equal,native_digest=after_task.digest if after_task else None,
      migration_state=completed.get('migration_state'),completed_state=completed.get('state'),
      sql_after=after,sql_unchanged=before==after,receipt_context_matches=bool(after_receipt and after_receipt['context_digest']==host.digest(target)))
    assert code==0 and current==target and after_status['state']=='stopped' and after_status.get('pid') is None
    assert after_task and not after_task.active and after_task.state!=0 and shape_equal
    assert completed.get('plan_revision')==REVISION and completed.get('state')=='committed'
    assert completed.get('migration_state')=='not_run_by_upgrade' and before==after
    result['status']='APPLIED_ONCE_CONFIRMED_NOT_STARTED'
except BaseException as exc:
    result['status']='UNCONFIRMED_NO_RETRY'
    result['failure']={'class':type(exc).__name__,'code':str(getattr(exc,'code','UNCLASSIFIED')),
      'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)]}
finally:
    for name in ('apply.stdout','apply.stderr'):
        if (PRIVATE/name).exists(): result[name+'_sha256']=sha(PRIVATE/name)
    save('apply-result.json',result)
print(json.dumps(result))
assert result['status']=='APPLIED_ONCE_CONFIRMED_NOT_STARTED'
