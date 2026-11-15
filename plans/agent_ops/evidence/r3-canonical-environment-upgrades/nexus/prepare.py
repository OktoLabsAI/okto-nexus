from pathlib import Path
import hashlib,json,subprocess,sys,zipfile,xml.etree.ElementTree as ET
import win32api,win32con,win32security
HERE=Path(__file__).resolve().parent
Q=Path('C:/Users/jpamb/AppData/Local/Temp/r3-status-fixed-campaign-package-ddwnb5vx')
HOME=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign/nexus-home')
EVIDENCE=Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-sonnet-useful03-native-permission-refusal/lifecycle/public')
def sha(p):
    digest=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(65536),b''): digest.update(chunk)
    return digest.hexdigest()
def save(name,value):
    with (HERE/name).open('x',encoding='utf-8') as f: json.dump(value,f,indent=2); f.write('\n')
# Execute only after Root supplies explicit restored proof pins. No defaults.
restore_path=Path(sys.argv[1]); restore_sha=sys.argv[2]
manifest_path=Path(sys.argv[3]); manifest_sha=sys.argv[4]
assert sha(restore_path)==restore_sha and sha(manifest_path)==manifest_sha
restored=json.loads(restore_path.read_text()); manifest=json.loads(manifest_path.read_text())
assert restored['status']=='EXACT_CODEX_0157_PAYLOAD_RESTORED'
assert restored['service_context_unchanged'] is True
assert manifest['file_count']==48 and manifest['matched_original_discovery'] is True and len(manifest['files'])==48
root=Path(manifest['target'])
assert root==Path('C:/Users/jpamb/AppData/Local/Temp/m1-native-discovery-iyoo0rs3/codex-0.157.0')
for relative,digest in manifest['files'].items():
    p=root/relative; assert p.resolve().is_relative_to(root.resolve()) and p.is_file() and sha(p)==digest
assert Path(sys.prefix).resolve()==(Q/'venv').resolve()
assert sha(Q/'installation.json')=='0055c57c33616c12ddfe78c12d1d940423c62f437a7722959976b7baf601b880'
installation=json.loads((Q/'installation.json').read_text()); count=0
for item in installation['wheels']:
    p=Q/item['path']; assert sha(p)==item['sha256']
    with zipfile.ZipFile(p) as z:
        for name in z.namelist():
            if name.startswith(('okto_nexus/','okto_nexus_connector/','nexus_connector_core/')) and not name.endswith('/'):
                assert (Q/'venv/Lib/site-packages'/name).read_bytes()==z.read(name); count+=1
owner=json.loads((EVIDENCE/'nexus-owner-selection.json').read_text())
proof=json.loads((EVIDENCE/'nexus-exit-proof.json').read_text())
assert owner['generation']=='f8d19439521b499275eee719e97c8e12' and proof['force_used'] is False
assert proof['cohort']==owner['cohort'] and set(proof['exits'])=={'parent','launcher','child'}
assert all(v['physical_exit'] is True and v['exit_code']==0 for v in proof['exits'].values())
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
from okto_nexus.adapters.outbound.service_manager.upgrade import for_lifecycle
service=resolve_local_service(['--home',str(HOME)],action='upgrade-plan')
host=for_lifecycle(service.adapter).host
assert sha(host.context_path)=='b4eaee8c2106f8130fe66d2818e563df709861acb459461310247f1fcab46d43'
status=host.status(); receipt,task=host.installed()
assert status['state']=='stopped' and status.get('pid') is None
assert host.instance_id==owner['instance_id'] and task and not task.active and task.state!=0
assert task.digest==receipt['native_digest']==owner['task']['digest']
marker=host.optional(host.run_path); shutdown=host.optional(host.shutdown_path)
assert marker['generation']==shutdown['generation']==owner['generation']
assert marker['state']=='drained' and shutdown['state']=='DRAINED'
def sql_hashes():
    files={p for p in HOME.rglob('*') if p.is_file() and (p.suffix in {'.db','.sqlite','.sqlite3'} or p.name.endswith(('-wal','-shm')))}
    if host.database.exists(): files.add(host.database)
    return {str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(files)}
paths=[host.context_path,host.installation_path,host.control_path,host.run_path,host.completed_path,host.shutdown_path]
before={str(p):sha(p) if p.exists() else None for p in paths}; sql_before=sql_hashes()
private=HERE/'private'; private.mkdir()
token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
try: sid=win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token,win32security.TokenUser)[0])
finally: token.Close()
acl=subprocess.run(['rtk','proxy','icacls',str(private),'/inheritance:r','/grant:r','*'+sid+':(OI)(CI)F'],capture_output=True)
assert acl.returncode==0
planfile=private/'nexus-upgrade-plan.json'
save('preflight.json',{'payloads_equal':count,'restored_files':48,'restore_result_sha256':restore_sha,
 'restore_manifest_sha256':manifest_sha,'physical_exit_proof_sha256':sha(EVIDENCE/'nexus-exit-proof.json'),
 'source_generation':owner['generation'],'canonical_state':status['state'],'instance_id':host.instance_id,
 'native_state':task.state,'native_active':task.active,'native_digest':task.digest,
 'selected_hashes_before':before,'sql_before':sql_before})
args=[sys.executable,'-I','-B','-X','utf8','-m','okto_nexus.adapters.inbound.cli.main','service','upgrade-plan','--home',str(HOME),
 '--python',sys.executable,'--output',str(planfile),'--json']
with (private/'stdout.txt').open('xb') as out,(private/'stderr.txt').open('xb') as err:
    process=subprocess.Popen(['rtk','proxy',*args],stdout=out,stderr=err); code=process.wait()
after={str(p):sha(p) if p.exists() else None for p in paths}; sql_after=sql_hashes()
result={'exit_code':code,'plan_exists':planfile.exists(),'selected_files_unchanged':before==after,'sql_unchanged':sql_before==sql_after,
 'selected_hashes_after':after,'sql_after':sql_after,'stdout_sha256':sha(private/'stdout.txt'),'stderr_sha256':sha(private/'stderr.txt'),
 'applied':False,'service_started':False,'provider_invoked':False}
if code==0 and planfile.is_file():
    doc=json.loads(planfile.read_text()); body=doc['plan']; candidate=body['candidate']
    assert body['component']=='server' and body['instance_id']==host.instance_id and body['source_generation']==owner['generation']
    assert candidate['package']['version']=='0.3.3' and candidate['core']['version']=='0.0.14'
    assert Path(body['target_context']['executable']).resolve()==Path(sys.executable).resolve()
    xml=ET.fromstring(body['source_native_xml']); ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    result.update(plan_revision=doc['plan_revision'],plan_sha256=sha(planfile),private_plan_path=str(planfile),
      source_generation=body['source_generation'],source_version=body['source_version'],source_core_version=body['source_core_version'],
      target_version=candidate['package']['version'],target_core_version=candidate['core']['version'],target_prefix=body['target_context']['environment_prefix'],
      source_native_digest=body['source_native_digest'],task_shape={'actions':len(xml.findall('t:Actions/*',ns)),
       'triggers':len(xml.findall('t:Triggers/*',ns)),'principals':len(xml.findall('t:Principals/*',ns))})
save('projection.json',result)
print(json.dumps(result))
assert code==0 and before==after and sql_before==sql_after
