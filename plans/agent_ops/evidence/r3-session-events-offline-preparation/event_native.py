"""Read-only own native metadata. No live API is called on import."""
from pathlib import Path
from datetime import datetime,timezone
import ctypes
from ctypes import wintypes
import hashlib,json,time,xml.etree.ElementTree as ET
ROLES=('parent','launcher','child')
def require(value,code):
    if not value:raise RuntimeError(code)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
class Process:
    def __init__(self, pid):
        self.pid, self.handle = pid, None
        self.k = k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k.OpenProcess.restype = wintypes.HANDLE
        k.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        k.GetProcessTimes.restype = wintypes.BOOL
        k.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = (wintypes.HANDLE,)
        k.CloseHandle.restype = wintypes.BOOL
        k.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k.GetExitCodeProcess.restype = wintypes.BOOL
        self.handle = k.OpenProcess(0x1000 | 0x100000, False, pid)
        require(bool(self.handle), 'PROCESS_HANDLE_UNAVAILABLE')
        try:
            fields = [wintypes.FILETIME() for _ in range(4)]
            require(k.GetProcessTimes(self.handle, *[ctypes.byref(v) for v in fields]), 'PROCESS_BIRTH_UNAVAILABLE')
            self.birth = (fields[0].dwHighDateTime << 32) | fields[0].dwLowDateTime
            buf, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
            require(k.QueryFullProcessImageNameW(self.handle, 0, buf, ctypes.byref(size)), 'PROCESS_IMAGE_UNAVAILABLE')
            self.image = str(Path(buf.value).resolve())
            require(not self.exited(), 'PROCESS_ALREADY_EXITED')
        except BaseException:
            self.close()
            raise

    def exited(self):
        value = self.k.WaitForSingleObject(self.handle, 0)
        require(value in (0, 258), 'PROCESS_WAIT_UNKNOWN')
        return value == 0

    def exit_code(self):
        require(self.exited(), 'PROCESS_STILL_ALIVE')
        value = wintypes.DWORD()
        require(self.k.GetExitCodeProcess(self.handle, ctypes.byref(value)), 'EXIT_CODE_UNKNOWN')
        return value.value

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None

def owned_path(path, root):
    root, path = Path(root).resolve(), Path(path)
    require(path.is_absolute() and path.resolve().is_relative_to(root), 'PATH_OUTSIDE_OWN_ROOT')
    # Refuse junction/reparse redirection even when it resolves back into root.
    for item in [path, *path.parents]:
        if item.exists():
            flags = getattr(item.lstat(), 'st_file_attributes', 0)
            require(not flags & 0x400, 'REPARSE_PATH_REFUSED')
        if item == root:
            break
    return path.resolve()

def secure_directory(path, root):
    """Protect only this campaign/driver-owned directory, never a personal home."""
    path = owned_path(path, root)
    path.mkdir(exist_ok=True)
    import ntsecuritycon
    import win32api
    import win32con
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    acl = win32security.ACL()
    inherit = win32con.OBJECT_INHERIT_ACE | win32con.CONTAINER_INHERIT_ACE
    for sid in (user, system):
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, inherit, ntsecuritycon.FILE_ALL_ACCESS, sid)
    win32security.SetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None)
    descriptor = win32security.GetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION)
    require(descriptor.GetSecurityDescriptorControl()[0] & 0x1000, 'PRIVATE_ACL_UNCONFIRMED')
    actual = descriptor.GetSecurityDescriptorDacl()
    require(actual is not None and actual.GetAceCount() == 2, 'PRIVATE_ACL_UNCONFIRMED')
    expected = {win32security.ConvertSidToStringSid(s) for s in (user, system)}
    seen = set()
    for index in range(actual.GetAceCount()):
        header, mask, sid = actual.GetAce(index)
        require(header[0] == win32security.ACCESS_ALLOWED_ACE_TYPE
            and header[1] & inherit == inherit and not header[1] & 0x10
            and mask == ntsecuritycon.FILE_ALL_ACCESS, 'PRIVATE_ACL_UNCONFIRMED')
        seen.add(win32security.ConvertSidToStringSid(sid))
    require(seen == expected, 'PRIVATE_ACL_UNCONFIRMED')
    return path

def iso(value):
    if isinstance(value,datetime):return value.astimezone(timezone.utc).isoformat()
    return None

def own_session_facts():
    import win32api,win32con,win32security,pythoncom,win32com.client
    token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
    try:
        sid=win32security.GetTokenInformation(token,win32security.TokenUser)[0]
        statistics=win32security.GetTokenInformation(token,win32security.TokenStatistics)
        session=win32security.GetTokenInformation(token,win32security.TokenSessionId)
    finally:token.Close()
    auth=statistics['AuthenticationId']
    logon=win32security.LsaGetLogonSessionData(auth)
    result={'principal_sha256':hashlib.sha256(win32security.ConvertSidToStringSid(sid).encode()).hexdigest(),
        'logon_authentication_id':str(auth),'session_id':int(session),'logon_time_utc':iso(logon.get('LogonTime')),
        'logon_type':logon.get('LogonType'),'last_boot_up_time_dmtf':None}
    # OS singleton metadata only, not Windows event history or process enumeration.
    pythoncom.CoInitialize()
    service=None
    try:
        service=win32com.client.GetObject(r'winmgmts:{impersonationLevel=impersonate}!\\.\root\cimv2')
        rows=service.ExecQuery('SELECT LastBootUpTime FROM Win32_OperatingSystem')
        values=[str(row.LastBootUpTime) for row in rows]
        require(len(values)==1,'BOOT_METADATA_NOT_UNIQUE');result['last_boot_up_time_dmtf']=values[0]
    except Exception as e:result['boot_metadata_error']=type(e).__name__
    finally:service=None;pythoncom.CoUninitialize()
    return result

def installation(P,name):
    if name=='nexus':
        from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
        root=Path(P['homes'][name]);service=ServerInstallation(root,root/'nexus.db')
    else:
        require(name=='connector','COMPONENT_INVALID')
        from okto_nexus_connector.platform.user_service import UserService
        service=UserService(Path(P['homes'][name]))
    require(service.name==P['tasks'][name],'OWN_PRINCIPAL_OR_TASK_CHANGED')
    return service

def task_projection(P,name,task):
    if task is None:return {'present':False,'name':P['tasks'][name]}
    root=ET.fromstring(task.xml);triggers=root.find('{*}Triggers')
    logons=[] if triggers is None else triggers.findall('{*}LogonTrigger')
    logon_enabled=bool(logons) and all(t.findtext('{*}Enabled','true').lower()=='true' for t in logons)
    return {'present':True,'name':P['tasks'][name],'digest':task.digest,'state':task.state,
        'enabled':task.enabled,'active':task.active,'last_result':task.last_result,
        'logon_trigger_enabled':logon_enabled,'restart_on_failure_present':root.find('.//{*}RestartOnFailure') is not None}

def exact_task_last_run(P,name,digest):
    if name=='nexus':from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
    else:from okto_nexus_connector.platform.windows_tasks import WindowsTasks
    from nexus_connector_core.user_service_definition import windows_definition_digest
    tasks=WindowsTasks()
    def observe(folder):
        task=tasks._task(folder,P['tasks'][name]);require(task is not None,'OWN_TASK_DISAPPEARED')
        require(windows_definition_digest(task.Xml)==digest,'TASK_DEFINITION_CHANGED')
        return iso(task.LastRunTime)
    return tasks._call(observe)

def normalize_cycle(value,name):
    require(isinstance(value,dict),'SUPERVISOR_CYCLE_UNAVAILABLE')
    out={k:value.get(k) for k in ('cycle_id','phase','attempts_started','child_acknowledged')}
    for role in ROLES:
        v=value.get(role);require(isinstance(v,dict) and type(v.get('pid')) is int and v['pid']>0,'COHORT_IDENTITY_INVALID')
        if name=='connector':
            token=v.get('birth_token');require(isinstance(token,str) and token.startswith('filetime:')
                and token[9:].isascii() and token[9:].isdigit(),'BIRTH_TOKEN_INVALID')
            birth=int(token[9:]);require(token=='filetime:'+str(birth),'BIRTH_TOKEN_NONCANONICAL')
        else:birth=v.get('birth')
        require(type(birth) is int and birth>0,'PROCESS_BIRTH_INVALID');out[role]={'pid':v['pid'],'birth':birth}
    return out

def read_cycle(P,name,service):
    if name=='nexus':
        from okto_nexus.adapters.outbound.service_manager.supervision import read_record
        value=read_record(Path(P['homes'][name]),service.receipt(),P['instance_ids'][name])
    else:
        from okto_nexus_connector.platform.service_supervision import read_cycle as read
        value=read(Path(P['homes'][name]),service.receipt())
    return normalize_cycle(value,name)

def canonical_status(P,name):
    if name=='nexus':
        from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
        home=Path(P['homes'][name]);value=inspect_local_server(home=home,database=home/'nexus.db',host='127.0.0.1',port=P['port'],timeout=1)
    else:
        from okto_nexus_connector.daemon import manager
        value=manager.status(Path(P['homes'][name]),timeout=1).to_json()
    fields=('state','reason','code','pid','generation','instance_id','ready_for_queries','storage_initialized',
        'accepting_work','admission','running','ipc_ok','draining','shutdown_outcome','supervisor')
    return {k:value.get(k) for k in fields if k in value}

def receipt_projection(P,name):
    root=Path(P['homes'][name]);paths={'run':root/'service-run.json',
        'shutdown':root/('service-shutdown.json' if name=='nexus' else 'run/shutdown.json')}
    result={}
    for label,path in paths.items():
        if not path.exists():result[label]={'present':False};continue
        try:
            require(not path.is_symlink() and path.stat().st_size<=65536,'RECEIPT_BOUND_EXCEEDED')
            raw=path.read_bytes();value=json.loads(raw)
            allowed=('revision','state','generation','pid','exit_code','pending','started_at','ended_at','shutdown_state')
            result[label]={'present':True,'sha256':hashlib.sha256(raw).hexdigest(),'fields':{k:value[k] for k in allowed if k in value and isinstance(value[k],(str,int,float,bool,type(None)))}}
        except Exception as e:result[label]={'present':True,'unconfirmed':True,'error_type':type(e).__name__}
    return result

def collect_component(P,name,*,retain=False,process=Process):
    result={'component':name,'instance_id_expected':P['instance_ids'][name],'cohort_confirmed':False,
        'active_work_count':None,'active_work_certainty':'NOT_QUERIED','productive_requests_selected':0}
    handles={}
    try:
        service=installation(P,name);task=service.tasks.read(service.name);result['task']=task_projection(P,name,task)
        if task is not None:service.observe()
        if task is not None:result['task']['last_run_time_utc']=exact_task_last_run(P,name,task.digest)
        result['canonical']=canonical_status(P,name);result['receipts']=receipt_projection(P,name)
        c=read_cycle(P,name,service);result['cohort']=c
        require(result['canonical'].get('instance_id')==P['instance_ids'][name]
            and result['canonical'].get('pid')==c['child']['pid'],'OWNER_COHORT_MISMATCH')
        for role in ROLES:
            h=process(c[role]['pid']);handles[role]=h
            require(h.birth==c[role]['birth'] and h.image in P['python_images']
                and sha(h.image)==P['python_images'][h.image],'PROCESS_IDENTITY_CHANGED')
        require(read_cycle(P,name,service)==c,'COHORT_CHANGED_DURING_CAPTURE')
        now=canonical_status(P,name)
        require(all(now.get(k)==result['canonical'].get(k) for k in ('pid','generation','instance_id')),'OWNER_CHANGED_DURING_CAPTURE')
        require(not any(h.exited() for h in handles.values()),'PROCESS_EXIT_DURING_CAPTURE')
        result['cohort_confirmed']=True
    except Exception as e:result['observation_error']=type(e).__name__
    if not retain or not result['cohort_confirmed']:
        for h in handles.values():h.close()
        handles={}
    return result,handles

def snapshot(P,*,retain=False):
    result={'utc':datetime.now(timezone.utc).isoformat(),'monotonic':time.monotonic(),
        'automatic_start_selected':False,'provider_calls':0,'components':{}}
    handles={}
    try:result['own_session']=own_session_facts()
    except Exception as e:result['own_session']={'unconfirmed':True,'error_type':type(e).__name__}
    for name in ('nexus','connector'):
        value,current=collect_component(P,name,retain=retain);result['components'][name]=value
        handles.update({name+'/'+r:h for r,h in current.items()})
    return result,handles
