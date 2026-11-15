from pathlib import Path
import hashlib,importlib,importlib.metadata,json,subprocess,sys,zipfile,xml.etree.ElementTree as ET
import win32api,win32con,win32security
HERE=Path(__file__).resolve().parent
Q=Path('C:/Users/jpamb/AppData/Local/Temp/r3-status-fixed-campaign-package-ddwnb5vx')
STATE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign/connector-state')
PROOF=Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence/r3-sonnet-authorized-current-force-stop/public/exit-proof.json')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert Path(sys.prefix).resolve()==(Q/'venv').resolve()
assert sha(Q/'installation.json')=='0055c57c33616c12ddfe78c12d1d940423c62f437a7722959976b7baf601b880'
installation=json.loads((Q/'installation.json').read_text())
count=0
for wheel in installation['wheels']:
    p=Q/wheel['path']; assert sha(p)==wheel['sha256']
    with zipfile.ZipFile(p) as z:
        for name in z.namelist():
            if name.startswith(('okto_nexus/','okto_nexus_connector/','nexus_connector_core/')) and not name.endswith('/'):
                assert (Q/'venv/Lib/site-packages'/name).read_bytes()==z.read(name); count+=1
proof=json.loads(PROOF.read_text())
assert proof['owner']['generation']=='fbc0042be355e83da5bb695a64de4910'
assert proof['owner']['pid']==39640 and proof['physical_exit_confirmed'] is True
assert set(proof['exits'])=={'parent','launcher','child'}
assert all(v['physical_exit'] is True and v['exit_code']==0 for v in proof['exits'].values())
from okto_nexus_connector.daemon.manager import _process_status
from okto_nexus_connector.platform.user_service import UserService
from okto_nexus_connector.platform.service_upgrade import for_instance
status=_process_status(STATE).to_json()
selected=UserService(STATE); receipt,task=selected.observe()
assert status['state']=='stopped' and status.get('pid') is None
assert receipt and task and not task.active and task.state!=0
assert selected.instance_id==proof['owner']['instance_id'] and selected.name==proof['task']['name']
assert task.digest==receipt['native_digest']==proof['task']['digest']
host=for_instance(STATE).host
paths=[host.context_path,host.installation_path,host.control_path,host.run_path,host.completed_path,host.shutdown_path]
before={str(p):sha(p) if p.exists() else None for p in paths}
private=HERE/'private'; private.mkdir()
token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
try: sid=win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token,win32security.TokenUser)[0])
finally: token.Close()
acl=subprocess.run(['rtk','proxy','icacls',str(private),'/inheritance:r','/grant:r','*'+sid+':(OI)(CI)F'],capture_output=True)
assert acl.returncode==0
planfile=private/'connector-upgrade-plan.json'
args=[sys.executable,'-I','-B','-X','utf8','-m','okto_nexus_connector.cli.main','--non-interactive','--json','--state-dir',str(STATE),'service','upgrade-plan','--python',sys.executable,'--output',str(planfile)]
preflight={'installed_payloads_equal':count,'source_generation':proof['owner']['generation'],
 'instance_id':selected.instance_id,'native_task_name':selected.name,'native_state':task.state,'native_active':task.active,
 'native_digest':task.digest,'canonical_state':status['state'],'canonical_pid':status.get('pid'),
 'physical_exit_proof_sha256':sha(PROOF),'installation_sha256':sha(Q/'installation.json'),'private_acl_current_user_only':True}
(HERE/'preflight.json').write_text(json.dumps(preflight,indent=2)+'\n')
with (private/'stdout.txt').open('wb') as out,(private/'stderr.txt').open('wb') as err:
    process=subprocess.Popen(['rtk','proxy',*args],stdout=out,stderr=err)
    code=process.wait()
after={str(p):sha(p) if p.exists() else None for p in paths}
projection={'exit_code':code,'plan_exists':planfile.exists(),'selected_files_unchanged':before==after,
 'selected_file_hashes_before':before,'selected_file_hashes_after':after,'preflight':preflight,
 'stdout_sha256':sha(private/'stdout.txt'),'stderr_sha256':sha(private/'stderr.txt'),
 'applied':False,'service_started':False,'provider_invoked':False}
if code==0 and planfile.is_file():
    doc=json.loads(planfile.read_text()); body=doc['plan']; candidate=body['candidate']
    assert body['source_generation']==proof['owner']['generation']
    assert body['instance_id']==selected.instance_id
    assert Path(body['target_context']['executable']).resolve()==Path(sys.executable).resolve()
    xml=ET.fromstring(body['source_native_xml']); ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    projection.update(plan_revision=doc['plan_revision'],plan_sha256=sha(planfile),private_plan_path=str(planfile),
      source_generation=body['source_generation'],source_version=body['source_version'],source_core_version=body['source_core_version'],
      target_version=candidate['package']['version'],target_core_version=candidate['core']['version'],
      target_prefix=body['target_context']['environment_prefix'],target_executable=body['target_context']['executable'],
      source_native_digest=body['source_native_digest'],task_shape={'actions':len(xml.findall('t:Actions/*',ns)),
       'triggers':len(xml.findall('t:Triggers/*',ns)),'principals':len(xml.findall('t:Principals/*',ns))})
(HERE/'projection.json').write_text(json.dumps(projection,indent=2)+'\n')
print(json.dumps(projection))
assert code==0 and before==after
