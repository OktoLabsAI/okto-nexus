from pathlib import Path
import json,sys,time,sqlite3,ctypes
from ctypes import wintypes
sys.path.insert(0,'C:/Users/jpamb/AppData/Local/Temp')
from m1_real_lifecycle import ROOT,C,P
from okto_nexus.adapters.inbound.cli.service import resolve_local_service
service=resolve_local_service(C['service_selection_args'])
expected_generation='188be445d44e96d483336ee424008e56'
expected_pid=45144
started=time.time();deadline=time.monotonic()+120
states=[];birth=None
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)];kernel.GetProcessTimes.restype=wintypes.BOOL
kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
def process_birth(pid):
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87:return None
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        stamps=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(s) for s in stamps]):raise ctypes.WinError(ctypes.get_last_error())
        return (stamps[0].dwHighDateTime<<32)|stamps[0].dwLowDateTime
    finally:kernel.CloseHandle(handle)
while True:
    value=service.inspect()
    assert value.get('generation') in (None,expected_generation)
    assert value.get('pid') in (None,expected_pid)
    current_birth=process_birth(expected_pid)
    live=current_birth is not None
    if birth is None and current_birth is not None:birth=current_birth
    if current_birth is not None:assert current_birth==birth
    row={'observed_at':time.time(),'state':value['state'],'generation':value.get('generation'),
         'pid':value.get('pid'),'pid_exists':live,'birth':current_birth,'admission':value.get('admission'),
         'shutdown':value.get('shutdown')}
    if not states or row['shutdown']!=states[-1]['shutdown'] or row['state']!=states[-1]['state']:states.append(row)
    if value['state']=='stopped' or time.monotonic()>=deadline:break
    time.sleep(1)
home=Path(P['paths']['server_home'])
metadata={}
for path in sorted((home/'core-runtime').glob('*.db')):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        data={}
        if 'owned_slot_reservations' in tables:
            cursor=db.execute('SELECT server_id,executor_id,session_id,operation_id,released FROM owned_slot_reservations')
            data['slots']=[dict(zip([d[0] for d in cursor.description],r)) for r in cursor]
        if 'operations_v2' in tables:
            cursor=db.execute('SELECT server_id,executor_id,session_id,operation_id,stage,possible_effect,retry_safe,error_code FROM operations_v2')
            data['operations']=[dict(zip([d[0] for d in cursor.description],r)) for r in cursor]
        metadata[path.name]=data
report={'started':started,'finished':time.time(),'observation_seconds':time.time()-started,
        'expected_generation':expected_generation,'expected_pid':expected_pid,'verified_birth':birth,
        'final_status':value,'transitions':states,'core_metadata':metadata,'mutations':0,
        'force_executed':False,'uninstall_executed':False}
(ROOT/'public/drain-observation-120s.json').write_text(json.dumps(report,indent=2))
if value['state']!='stopped':
    step=next(s for s in C['steps'] if s['component']=='nexus' and s['action']=='stop')
    argv=step['argv']+['--force','--expected-generation',expected_generation]
    shutdown=value.get('shutdown') or {}
    proposal={'status':'PREPARED_NOT_EXECUTED_REQUIRES_EXPLICIT_AUTHORIZATION','argv':argv,
       'task_name':step['task_name'],'generation':expected_generation,'pid':expected_pid,'birth':birth,
       'readiness':{'state':value['state'],'admission':value.get('admission'),
                    'force_available':shutdown.get('force_available'),'deadline_expired':shutdown.get('deadline_monotonic',float('inf'))<time.monotonic()},
       'pending_resources':shutdown.get('resources',[]),
       'then_only_after_confirmed_exit':next(s for s in C['steps'] if s['component']=='nexus' and s['action']=='uninstall')['argv'],
       'effects':['Forced containment of this exact owned generation can terminate retained tasks while reconciliation remains UNKNOWN.',
                  'Retain all journals and honest terminal states; native turn CANCELLED and session CLOSED do not prove service process exit.',
                  'No other task/process, no extra native/provider turn, no checkpoint reset.'],
       'basis':'Force was explicitly excluded from v7; this document is a concrete recovery proposal only.'}
    (ROOT/'public/force-recovery-proposal.json').write_text(json.dumps(proposal,indent=2))
print(json.dumps({'state':value['state'],'pid':value.get('pid'),'birth':birth,'observation_seconds':report['observation_seconds'],'resources':(value.get('shutdown') or {}).get('resources',[]),'core_metadata':metadata}))
