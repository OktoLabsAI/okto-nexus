from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
HOME=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign/nexus-home')
from okto_nexus.adapters.outbound.service_manager.identity import server_instance_id
assert Path(sys.prefix).resolve()==(HERE/'venv').resolve()
path=HOME/'service-context.json'
before=hashlib.sha256(path.read_bytes()).hexdigest()
assert before=='b4eaee8c2106f8130fe66d2818e563df709861acb459461310247f1fcab46d43'
run=subprocess.run(['rtk','proxy',sys.executable,'-I','-B','-X','utf8','-m',
 'okto_nexus.adapters.inbound.cli.main','service','status','--home',str(HOME),'--json'],
 capture_output=True,text=True,encoding='utf-8',timeout=30)
result=json.loads(run.stdout)
after=hashlib.sha256(path.read_bytes()).hexdigest()
projection={'exit_code':run.returncode,'state':result.get('state'),'reason':result.get('reason'),
 'instance_id':result.get('instance_id'),'expected_instance_id':server_instance_id(HOME,HOME/'nexus.db'),
 'context_before_sha256':before,'context_after_sha256':after,'context_unchanged':before==after,
 'stderr_bytes':len(run.stderr.encode('utf-8')),'action':'service status --home <owned-home> --json',
 'read_only':True,'original_installed_campaign_modified':False}
(HERE/'real-status-projection.json').write_text(json.dumps(projection,indent=2)+'\n',encoding='utf-8')
print(json.dumps(projection))
assert run.returncode==0 and result['state']=='stopped' and result['reason']=='NO_SERVICE_OWNER'
assert projection['instance_id']==projection['expected_instance_id'] and before==after
