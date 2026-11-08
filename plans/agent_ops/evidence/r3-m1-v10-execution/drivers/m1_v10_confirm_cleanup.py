from pathlib import Path
import json,time
from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
R=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign')
owned=json.loads((R/'public/nexus-owner-selection.json').read_text())
proof=json.loads((R/'public/nexus-exit-proof.json').read_text())
drain=json.loads((R/'nexus-home/service-shutdown.json').read_text())
assert proof['retained_handle'] and proof['exit_confirmed'] and proof['wait_result']==0
assert not proof['force_used'] and drain['state']=='DRAINED'
assert drain['generation']==proof['generation']==owned['generation']
assert proof['birth_filetime']==owned['birth_filetime'] and proof['pid']==owned['pid']
task=WindowsTasks().read(owned['task']['name'])
assert task and task.state in (1,3) and task.digest==owned['task']['digest']
v={'task_name':owned['task']['name'],'owned_pid_birth_exit_confirmed':True,'task_stopped_confirmed':True,'force_used':False,'task_state':task.state,'task_digest':task.digest,'exit_proof':proof,'drain':drain,'time':time.time()}
with (R/'public/cleanup-nexus.json').open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)
print(json.dumps(v))
