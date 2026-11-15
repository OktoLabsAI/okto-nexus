"""One explicitly selected Windows event. Never retries, starts services or logs in."""
import argparse,ctypes,json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from automation_contract import event_command,validate_window,require
from attempt_contract import digest,validate_attempt

def native_dispatch(command):
    if isinstance(command,list):
        # Exact derived shutdown argv only; no shell, /f or positive/default /t.
        result=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return {'command_return_code':result.returncode,'event_proven':False}
    import win32api,win32con,win32security
    require(command['api']=='powrprof.SetSuspendState' and command['arguments']==[False,False,False],'SUSPEND_COMMAND_CHANGED')
    token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY|win32con.TOKEN_ADJUST_PRIVILEGES)
    old=None
    try:
        privilege=win32security.LookupPrivilegeValue(None,'SeShutdownPrivilege')
        win32api.SetLastError(0)
        old=win32security.AdjustTokenPrivileges(token,False,[(privilege,win32con.SE_PRIVILEGE_ENABLED)])
        require(win32api.GetLastError()==0,'OWN_SHUTDOWN_PRIVILEGE_NOT_ASSIGNED')
        library=ctypes.WinDLL('powrprof',use_last_error=True)
        fn=library.SetSuspendState;fn.argtypes=[ctypes.c_ubyte]*3;fn.restype=ctypes.c_ubyte
        ok=bool(fn(0,0,0))
        return {'api_return_nonzero':ok,'winerror':None if ok else ctypes.get_last_error(),'event_proven':False}
    finally:
        if old is not None:win32security.AdjustTokenPrivileges(token,False,old)
        token.Close()

def execute(P,N,O,plan_sha,*,clock=lambda:datetime.now(timezone.utc),dispatch=native_dispatch):
    event=P['selected_event'];directory=Path(P['root'])/'evidence'/event
    before_path=directory/'before.json';before=O.read(before_path);before_sha=digest(before_path)
    require(before.get('plan_sha256')==plan_sha and before.get('event_id')==event,'BEFORE_SELECTION_CHANGED')
    require(not (directory/'event-attempt.json').exists() and not (directory/'event-attempt.json.writing').exists(),
            'EVENT_ALREADY_RESERVED_NO_RETRY')
    require(not (directory/'after.reserved').exists() and not (directory/'after.json').exists(),'AFTER_ALREADY_SELECTED')
    current,handles=N.snapshot(P,retain=True)
    try:
        require(set(handles)==set(O.expected_handles(before)),'SIX_CURRENT_HANDLES_REQUIRED')
        require(all(O.ready(current['components'][name]) for name in O.NAMES),'BOTH_READY_BEFORE_EVENT_REQUIRED')
        require(current['own_session']['principal_sha256']==before['own_session']['principal_sha256']
            and current['own_session']['logon_authentication_id']==before['own_session']['logon_authentication_id'],
            'OWN_LOGON_CHANGED_BEFORE_EVENT')
        require(O.expected_handles(current)==O.expected_handles(before),'BEFORE_COHORT_CHANGED')
        for name in O.NAMES:
            now=current['components'][name];old=before['components'][name]
            require(now['task']['digest']==old['task']['digest']==P['task_digests'][name],'TASK_CHANGED_BEFORE_EVENT')
            require(all(now['canonical'].get(k)==old['canonical'].get(k) for k in ('pid','generation','instance_id')),
                    'OWNER_CHANGED_BEFORE_EVENT')
        require(not any(h.exited() for h in handles.values()),'OWNER_EXIT_BEFORE_EVENT')
        issued=clock();principal=current['own_session']['principal_sha256']
        validate_window(P['window'],issued,principal)
        attempt={'state':'RESERVED_BEFORE_OS_CALL','event_id':event,'plan_sha256':plan_sha,'before_sha256':before_sha,
            'principal_sha256':principal,'window':P['window'],'issued_utc':issued.isoformat(),
            'command':event_command(event,r'C:\Windows\System32'),'no_force_apps':True,'automatic_next_event':False,
            'no_retry':True,'event_proven':False}
        validate_attempt(P,before,before_sha,plan_sha,attempt)
        O.save(directory/'event-attempt.json',attempt)  # exclusive+fsync+atomic rename
        # A time/identity change during durable publication consumes the attempt
        # but refuses the effect; it never creates a replacement attempt.
        try:
            validate_window(P['window'],clock(),principal)
            require(not any(h.exited() for h in handles.values()),'OWNER_EXIT_AFTER_RESERVATION')
        except Exception as error:
            O.save(directory/'event-command-returned.json',{'state':'REFUSED_BEFORE_OS_CALL','exception_class':type(error).__name__,
                'attempt_sha256':digest(directory/'event-attempt.json'),'retry_selected':False,'event_proven':False})
            raise
        try:result=dispatch(attempt['command'])
        except Exception as error:
            O.save(directory/'event-command-returned.json',{'state':'COMMAND_UNCONFIRMED','exception_class':type(error).__name__,
                'attempt_sha256':digest(directory/'event-attempt.json'),'retry_selected':False,'event_proven':False})
            raise
        O.save(directory/'event-command-returned.json',dict(result,attempt_sha256=digest(directory/'event-attempt.json'),
            retry_selected=False,event_proven=False))
        return {'state':'COMMAND_RETURNED_EVENT_UNPROVEN','event_id':event,'event_proven':False}
    finally:
        for handle in handles.values():handle.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--sha256',required=True)
    parser.add_argument('--execute-selected-event',action='store_true');args=parser.parse_args()
    require(args.execute_selected_event,'EXPLICIT_EVENT_SELECTION_REQUIRED')
    from collect import load
    P,N,O,H=load(args.plan,args.sha256)
    print(json.dumps(execute(P,N,O,args.sha256)))

if __name__=='__main__':main()
