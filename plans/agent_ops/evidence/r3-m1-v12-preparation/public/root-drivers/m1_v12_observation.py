"""Select the exact service owner, then retain its physical process handle."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import gate, main_guard, parser, public_save, read_json, require, require_tags, tags

IDENTITY = ('pid', 'generation', 'instance_id')


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


class PhysicalProcess:
    def __init__(self, pid):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        k = self.kernel
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        k.GetProcessTimes.restype = wintypes.BOOL
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        self.handle = k.OpenProcess(0x00100000 | 0x1000, False, pid)
        require(bool(self.handle), 'PROCESS_HANDLE_UNAVAILABLE')

    def birth(self):
        fields = [wintypes.FILETIME() for _ in range(4)]
        require(self.kernel.GetProcessTimes(self.handle, *[ctypes.byref(v) for v in fields]), 'PROCESS_BIRTH_UNAVAILABLE')
        return (fields[0].dwHighDateTime << 32) | fields[0].dwLowDateTime

    def wait(self, milliseconds):
        result = self.kernel.WaitForSingleObject(self.handle, milliseconds)
        require(result in (0, 258), 'PROCESS_WAIT_UNCONFIRMED')
        return result == 0

    def close(self):
        self.kernel.CloseHandle(self.handle)


def select(context, component, *, observe=status, process=PhysicalProcess):
    first = observe(context, component)
    handle = process(first['pid'])
    try:
        birth = handle.birth()
        require(not handle.wait(0), 'OWNER_ALREADY_EXITED')
        same_owner(first, observe(context, component))
    finally:
        handle.close()
    value = {**first, **tags(context), 'birth_filetime': birth, 'selected_at': time.time()}
    public_save(context, component + '-owner-selection.json', value)
    return value


def watch(context, component, seconds, *, observe=status, process=PhysicalProcess, clock=time.monotonic):
    require(type(seconds) is int and 1 <= seconds <= 3600, 'WATCH_BOUND_INVALID')
    selected = read_json(context.ROOT / 'public' / (component + '-owner-selection.json'))
    require_tags(selected, context)
    require(selected['component'] == component, 'COMPONENT_CHANGED')
    handle = process(selected['pid'])
    try:
        require(handle.birth() == selected['birth_filetime'], 'PROCESS_BIRTH_CHANGED')
        same_owner(selected, observe(context, component))
        public_save(context, component + '-exit-watch-started.json', {
            **{k: selected[k] for k in IDENTITY}, 'birth_filetime': selected['birth_filetime'],
            'maximum_wait_seconds': seconds, 'started_at': time.time()})
        deadline = clock() + seconds
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                public_save(context, component + '-exit-watch-timeout.json', {
                    'exit_confirmed': False, 'force_used': False, 'observed_at': time.time()})
                raise TimeoutError('Physical exit was not observed within the selected watch bound')
            if handle.wait(max(1, min(1000, int(remaining * 1000)))):
                break
        proof = {**{k: selected[k] for k in IDENTITY}, 'component': component,
            'birth_filetime': selected['birth_filetime'], 'retained_handle': True,
            'exit_confirmed': True, 'wait_result': 0, 'force_used': False,
            'observed_at': time.time(), 'observer_only': True}
        public_save(context, component + '-exit-proof.json', proof)
        return proof
    finally:
        handle.close()


def main():
    p = parser()
    p.add_argument('component', choices=('nexus', 'connector'))
    p.add_argument('operation', choices=('select', 'watch'))
    p.add_argument('--watch-seconds', type=int, default=1800)
    args = p.parse_args()
    context = gate(args)
    result = select(context, args.component) if args.operation == 'select' else watch(context, args.component, args.watch_seconds)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
