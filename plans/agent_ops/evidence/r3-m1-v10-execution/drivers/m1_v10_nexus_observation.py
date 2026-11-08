from pathlib import Path
import json,ctypes,sys,time,hashlib
from ctypes import wintypes
R=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v10-bundle-pscf18t5/campaign')
B=R.parent/'draft';P=json.loads((B/'m1-codex-campaign-proposal-v10.json').read_text());C=json.loads((B/'proposed-commands.json').read_text())
assert hashlib.sha256((B/'m1-codex-campaign-proposal-v10.json').read_bytes()).hexdigest()=='90c2ed2ca18e7fd86380c614e516a5f8975af2a2052b56a3609004be4814405a'
from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
H=Path(P['paths']['server_home'])
def status():return inspect_local_server(home=H,database=H/'nexus.db',host='127.0.0.1',port=56237,timeout=5)
def save(name,v):
    with (R/'public'/name).open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
k.CloseHandle.argtypes=[wintypes.HANDLE]
k.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)];k.GetProcessTimes.restype=wintypes.BOOL
k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.WaitForSingleObject.restype=wintypes.DWORD
def birth(handle):
    fields=[wintypes.FILETIME() for _ in range(4)]
    assert k.GetProcessTimes(handle,*[ctypes.byref(v) for v in fields])
    return (fields[0].dwHighDateTime<<32)|fields[0].dwLowDateTime
if sys.argv[1]=='status':
    raw=status();v={key:raw.get(key) for key in ('state','reason','instance_id','generation','pid','ready_for_queries','supervisor')}
    task=WindowsTasks().read(C['tasks']['nexus']['name'])
    v['task']={'name':C['tasks']['nexus']['name'],'state':task.state,'digest':task.digest} if task else None
    v['observed_at']=time.time();save('nexus-status-'+str(time.time_ns())+'.json',v)
    if v['state']=='ready' and not (R/'public/nexus-owner-selection.json').exists():
        handle=k.OpenProcess(0x00100000|0x1000,False,v['pid']);assert handle
        try:v['birth_filetime']=birth(handle)
        finally:k.CloseHandle(handle)
        after=status();assert all(after.get(key)==v[key] for key in ('instance_id','generation','pid'))
        save('nexus-owner-selection.json',v)
    print(json.dumps(v))
elif sys.argv[1]=='watch':
    v=json.loads((R/'public/nexus-owner-selection.json').read_text())
    handle=k.OpenProcess(0x00100000|0x1000,False,v['pid']);assert handle
    try:
        assert birth(handle)==v['birth_filetime']
        after=status();assert all(after.get(key)==v[key] for key in ('instance_id','generation','pid'))
        save('nexus-exit-watch-started.json',{'pid':v['pid'],'birth_filetime':v['birth_filetime'],'generation':v['generation'],'time':time.time()})
        while True:
            result=k.WaitForSingleObject(handle,1000)
            if result==0:break
            assert result==258, result
        proof={key:v[key] for key in ('pid','generation','birth_filetime','instance_id')}
        proof.update(exit_confirmed=True,wait_result=0,retained_handle=True,observed_at=time.time(),force_used=False)
        save('nexus-exit-proof.json',proof);print(json.dumps(proof))
    finally:k.CloseHandle(handle)
else:raise ValueError('only status or watch')
