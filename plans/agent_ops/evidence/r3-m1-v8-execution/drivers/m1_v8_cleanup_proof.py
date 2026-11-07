import ctypes, json, pathlib, subprocess, datetime
from ctypes import wintypes
from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server, _held
from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
R=pathlib.Path('C:/Users/jpamb/AppData/Local/Temp/m1-fresh-v8-pg0b6zbf/campaign')
H=R/'nexus-home'
prior=json.loads((R/'public/nexus-status-1794095382.973709.json').read_text())
assert prior['state']=='ready' and prior['pid']==9760
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
k.CloseHandle.argtypes=[wintypes.HANDLE]
ctypes.set_last_error(0)
handle=k.OpenProcess(0x00100000|0x1000,False,prior['pid'])
err=ctypes.get_last_error()
if handle:k.CloseHandle(handle)
assert not handle and err==87, ('PROCESS_ABSENCE_NOT_PROVEN',err)
q=subprocess.run(['powershell','-NoProfile','-Command',"$ErrorActionPreference='Stop'; $items=@(Get-CimInstance Win32_Process -Filter 'ProcessId=9760'); ConvertTo-Json -Compress -InputObject @{query_succeeded=$true;process_count=$items.Count}"],capture_output=True,check=True)
cim=json.loads(q.stdout); assert cim=={'query_succeeded':True,'process_count':0}
status=inspect_local_server(home=H,database=H/'nexus.db',host='127.0.0.1',port=49807)
assert status['state']=='stopped' and status['reason']=='NO_SERVICE_OWNER'
guards=[_held(H/'nexus.serve.guard'),_held(H/'nexus.db.serve.guard')]; assert guards==[False,False]
task=WindowsTasks().read(prior['user_service']['name'])
assert task and task.state in (1,3) and task.digest==prior['user_service']['definition_digest']
shutdown=json.loads((H/'service-shutdown.json').read_text());assert shutdown['generation']==prior['generation'] and shutdown['state']=='DRAINED'
logs=[json.loads(s) for s in (H/'logs/service.jsonl').read_text().splitlines()]
assert any(v.get('code')=='SERVICE_EXIT' and v.get('generation')==prior['generation'] and v.get('state')=='DRAINED' for v in logs)
proof={'task_name':prior['user_service']['name'],'owned_pid_birth_exit_confirmed':True,'task_stopped_confirmed':True,'force_used':False,
 'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pid':prior['pid'],'generation':prior['generation'],
 'birth_token':None,'birth_observed':False,'retained_handle':False,'exit_proof_method':'previously_owned_nonzero_pid_now_absent',
 'exit_proof_limit':'No historical birth comparison or signaled handle is claimed. Absence of the previously owned nonzero PID proves that no process with any birth at that PID survives at observation.',
 'open_process_error':err,'cim':cim,'guards_held':guards,'status':{'state':status['state'],'reason':status['reason']},
 'task_state':task.state,'task_digest':task.digest,'shutdown':shutdown,'service_exit_observed':True}
with (R/'public/cleanup-nexus.json').open('x') as f:json.dump(proof,f,indent=2)
print(json.dumps(proof))
