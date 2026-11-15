"""Exact qualified function reuse, selected namespace only; no effects on import."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import time
from urllib.parse import urlsplit
from request_context import require, sha, read_json, public_save, require_tags
IDENTITY=('pid','generation','instance_id')
ROLES=('parent','launcher','child')
def endpoint(context):
    origin = urlsplit(context.P['topology']['origin'])
    require(origin.scheme == 'http' and origin.hostname == '127.0.0.1' and origin.port
        and origin.username is None and origin.password is None and not origin.query and not origin.fragment,
        'FINITE_LOOPBACK_ORIGIN_REQUIRED')
    return origin.hostname, origin.port

def status(context, component):
    expected = context.C['tasks'][component]
    if component == 'nexus':
        from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
        from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation, SUPERVISOR
        home = Path(context.P['paths']['server_home'])
        _, task = ServerInstallation(home, home / 'nexus.db').observe()
        host, port = endpoint(context)
        raw = inspect_local_server(home=home, database=home / 'nexus.db', host=host, port=port, timeout=5)
        require(raw.get('state') == 'ready' and raw.get('ready_for_queries') is True
            and raw.get('supervisor') == SUPERVISOR, 'NEXUS_OWNER_NOT_READY')
        value = {k: raw.get(k) for k in IDENTITY}
    else:
        require(component == 'connector', 'COMPONENT_INVALID')
        from okto_nexus_connector.daemon import manager
        from okto_nexus_connector.platform.user_service import UserService, SUPERVISOR
        root = Path(context.P['paths']['connector_state'])
        _, task = UserService(root).observe()
        raw = manager.status(root, timeout=5)
        require(raw.state == 'ready' and raw.running and raw.ipc_ok and not raw.draining
            and raw.supervisor == SUPERVISOR, 'CONNECTOR_OWNER_NOT_READY')
        value = {k: getattr(raw, k) for k in IDENTITY}
    require(task is not None and task.enabled and task.active, 'OWN_TASK_NOT_ACTIVE')
    require(value['instance_id'] == expected['instance_id'] and type(value['pid']) is int
        and value['pid'] > 0 and isinstance(value['generation'], str) and value['generation'], 'OWNER_IDENTITY_INVALID')
    value.update(task={'name': expected['name'], 'state': task.state, 'digest': task.digest}, component=component)
    return value

def canonical_absence(context, component):
    if component == 'nexus':
        from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
        home = Path(context.P['paths']['server_home'])
        host, port = endpoint(context)
        value = inspect_local_server(home=home, database=home / 'nexus.db', host=host, port=port, timeout=2)
    else:
        require(component == 'connector', 'COMPONENT_INVALID')
        from okto_nexus_connector.daemon import manager
        value = manager._process_status(Path(context.P['paths']['connector_state']), timeout=2).to_json()
    return validate_canonical_absence(context, component, value)

def validate_canonical_absence(context, component, value):
    require(component in ('nexus', 'connector'), 'COMPONENT_INVALID')
    # Installed Connector DaemonStatus has generation='' when no owner exists.
    # Preserve that representation; None/False/0/nonempty are not equivalent.
    generation_absent = (value.get('generation') is None if component == 'nexus'
                         else value.get('generation') == '' and value.get('running') is False
                         and value.get('ipc_ok') is False)
    require(value.get('state') == 'stopped' and value.get('reason') == 'NO_SERVICE_OWNER'
        and value.get('instance_id') == context.C['tasks'][component]['instance_id']
        and value.get('pid') is None and generation_absent, 'CANONICAL_OWNER_ABSENCE_UNCONFIRMED')
    keys = ('state', 'reason', 'instance_id', 'pid', 'generation')
    if component == 'connector':
        keys += ('running', 'ipc_ok')
    return {k: value.get(k) for k in keys}

def same_owner(before, after):
    require(all(before.get(k) == after.get(k) for k in IDENTITY)
        and before.get('component') == after.get('component')
        and before['task']['name'] == after['task']['name']
        and before['task']['digest'] == after['task']['digest'], 'OWNER_CHANGED')

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

def installation(context):
    from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
    home = Path(context.P['paths']['server_home'])
    return ServerInstallation(home, home / 'nexus.db')

def cycle(context):
    from okto_nexus.adapters.outbound.service_manager.supervision import read_record
    service = installation(context)
    value = read_record(Path(context.P['paths']['server_home']), service.receipt(), context.C['tasks']['nexus']['instance_id'])
    require(isinstance(value, dict), 'SUPERVISOR_RECORD_MISSING')
    result = {k: value.get(k) for k in ('cycle_id', 'phase', 'attempts_started', 'child_acknowledged')}
    for role in ROLES:
        identity = value.get(role)
        require(isinstance(identity, dict) and type(identity.get('pid')) is int and identity['pid'] > 0
            and type(identity.get('birth')) is int and identity['birth'] > 0, 'SUPERVISOR_IDENTITY_MISSING')
        result[role] = {k: identity[k] for k in ('pid', 'birth')}
    return result

def same_cycle(before, after):
    require(all(before.get(k) == after.get(k) for k in ('cycle_id', 'attempts_started', *ROLES)), 'SUPERVISOR_COHORT_CHANGED')

def capture(context, *, observe=status, read_cycle=cycle, process=Process):
    before = observe(context, 'nexus')
    projected = read_cycle(context)
    require(projected['phase'] == 'running' and projected['child_acknowledged'] is True
        and projected['child']['pid'] == before['pid'], 'READY_HANDSHAKE_REQUIRED')
    handles = {}
    try:
        for role in ROLES:
            identity = projected[role]
            handle = process(identity['pid']); handles[role] = handle
            pins = context.installed['python_images']
            require(handle.birth == identity['birth'] and handle.image in pins
                and sha(handle.image) == pins[handle.image], 'COHORT_IMAGE_OR_BIRTH_CHANGED')
        require(read_cycle(context) == projected, 'SUPERVISOR_CHANGED_DURING_CAPTURE')
        same_owner(before, observe(context, 'nexus'))
        require(not any(h.exited() for h in handles.values()), 'COHORT_EXIT_DURING_CAPTURE')
        return {**before, 'cohort': projected, 'selected_at': time.time()}, handles
    except BaseException:
        for handle in handles.values(): handle.close()
        raise

def current_ready(context):
    selected = read_json(context.PUBLIC / 'nexus-owner-selection.json'); require_tags(selected, context)
    started = read_json(context.PUBLIC / 'nexus-exit-watch-started.json'); require_tags(started, context)
    require(started['cohort'] == selected['cohort'] and started['retained_roles'] == list(ROLES)
        and not (context.PUBLIC / 'nexus-exit-proof.json').exists()
        and not (context.PUBLIC / 'nexus-exit-watch-timeout.json').exists(), 'LIVE_COHORT_OBSERVER_REQUIRED')
    observer = Process(started['observer']['pid'])
    try:
        require(observer.birth == started['observer']['birth'] and observer.image in context.installed['python_images']
            and sha(observer.image) == context.installed['python_images'][observer.image], 'OBSERVER_IDENTITY_CHANGED')
    finally: observer.close()
    same_owner(selected, status(context, 'nexus'))
    now = cycle(context); same_cycle(selected['cohort'], now)
    require(now['phase'] == 'running' and now['child_acknowledged'] is True, 'CURRENT_COHORT_NOT_READY')
    return selected

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
