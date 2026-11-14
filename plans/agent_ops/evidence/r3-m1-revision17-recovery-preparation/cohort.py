"""Read-only supervisor cohort observation; no termination rights or service effects."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import require, read_json, public_save, require_tags, sha, gate, parser, main_guard
from m1_v14_observation import status, same_owner, canonical_absence

ROLES = ('parent', 'launcher', 'child')

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
    return result  # token, nonce, command lines, and environment never leave the product validator

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

def allow_passive_observation(result):
    require(result.get('component') == 'nexus' and result.get('action') == 'start', 'START_RESULT_REQUIRED')
    # The original CLI exit remains evidence. This authorizes no second start.
    require(result.get('returncode') == 0 or (result.get('returncode') == 3
        and result.get('reported_code') in (None, 'SERVICE_UNREACHABLE')
        and result.get('wait_timed_out') is True
        and result.get('reported_reason') in ('STARTUP_PENDING','CONCURRENT_START','SERVICE_UNREACHABLE',
            'INSTANCE_OWNERSHIP_UNCONFIRMED','INSTANCE_METADATA_UNAVAILABLE','SUPERVISOR_PENDING')
        and result.get('reported_state') in ('starting', 'unknown', 'degraded')),
        'POSITIVE_START_FAILURE_NOT_RETRYABLE')

def readiness_probe(context):
    from okto_nexus.adapters.outbound.service_manager.inspection import inspect_local_server
    from m1_v14_observation import endpoint
    home=Path(context.P['paths']['server_home']);host,port=endpoint(context)
    _,task=installation(context).observe()  # definition/context failures propagate immediately
    require(task is not None,'START_TASK_MISSING')
    raw=inspect_local_server(home=home,database=home/'nexus.db',host=host,port=port,timeout=5)
    require(raw.get('instance_id')==context.C['tasks']['nexus']['instance_id'],'READINESS_INSTANCE_CHANGED')
    if raw.get('state')=='ready':return status(context,'nexus')
    require(raw.get('state') in ('starting','unknown','degraded')
        and raw.get('reason') in ('STARTUP_PENDING','CONCURRENT_START','SERVICE_UNREACHABLE',
            'INSTANCE_OWNERSHIP_UNCONFIRMED','INSTANCE_METADATA_UNAVAILABLE','SUPERVISOR_PENDING'),
        'READINESS_POSITIVE_FAILURE')
    return None

def await_ready(context, *, observe=readiness_probe, clock=time.monotonic, sleep=time.sleep):
    result = read_json(context.PUBLIC / 'lifecycle-nexus-start-result.json')
    allow_passive_observation(result)
    deadline = clock() + 180
    while clock() < deadline:
        value = observe(context)
        if value is not None:
            require(clock() < deadline, 'PASSIVE_READINESS_DEADLINE')
            return value
        sleep(min(.25, max(0, deadline - clock())))
    raise RuntimeError('PASSIVE_READINESS_UNCONFIRMED')

def watch(context, seconds, *, clock=time.monotonic, sleep=time.sleep):
    require(type(seconds) is int and 1 <= seconds <= 3600, 'WATCH_BOUND_INVALID')
    require(not (context.PUBLIC / 'nexus-owner-selection.json').exists(), 'COHORT_ALREADY_SELECTED')
    await_ready(context)
    selected, handles = capture(context)
    try:
        observer = Process(os.getpid())
        try: observer_identity = {'pid': os.getpid(), 'birth': observer.birth}
        finally: observer.close()
        public_save(context, 'nexus-owner-selection.json', selected)
        public_save(context, 'nexus-exit-watch-started.json', {**selected, 'maximum_wait_seconds': seconds,
            'retained_roles': list(ROLES), 'terminate_right': False, 'observer': observer_identity})
        deadline = clock() + seconds
        while not all(h.exited() for h in handles.values()):
            if clock() >= deadline:
                public_save(context, 'nexus-exit-watch-timeout.json', {'exit_confirmed': False,
                    'force_used': False, 'observed_at': time.time()})
                raise RuntimeError('COHORT_EXIT_UNCONFIRMED')
            sleep(.2)
        same_cycle(selected['cohort'], cycle(context))
        proof = {**selected, 'retained_handle': True, 'exit_confirmed': True, 'force_used': False,
            'processes': {role: {'pid': h.pid, 'birth_filetime': h.birth, 'exit_code': h.exit_code(),
                'physical_exit_confirmed': True, 'terminate_right': False} for role, h in handles.items()},
            'observed_at': time.time(), 'runtime_work_settlement': 'NOT_ASSERTED'}
        public_save(context, 'nexus-exit-proof.json', proof)
        return proof
    finally:
        for handle in handles.values(): handle.close()

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

def recovery_ready(context):
    """One narrow bounded query-only current-generation readiness projection."""
    current_ready(context)
    sys.path.insert(0, str(context.modules))
    from independent_journal import ReadOnly
    expected = context.P['adoption']['expected_scope']
    reader = ReadOnly(context.ROOT)
    try:
        with reader.open(Path(context.P['paths']['server_home']) / 'nexus.db') as db:
            rows = [dict(row) for row in db.execute('''SELECT e.generation,e.control_state,
                r.generation AS recovery_generation,r.state AS recovery_state
                FROM execution_executors e JOIN execution_agent_recovery r
                ON r.server_id=e.server_id AND r.executor_id=e.executor_id
                WHERE e.server_id=? AND e.executor_id=? AND r.agent_id=? LIMIT 2''',
                (expected['server_id'], expected['executor_id'], expected['agent_id']))]
        require(len(rows) == 1, 'RECOVERY_ROW_MISSING')
        row = rows[0]
        require(type(row['generation']) is int and row['generation'] > context.amendment['predecessor_connection_generation']
            and row['control_state'] == 'CONTROL_READY' and row['recovery_generation'] == row['generation']
            and row['recovery_state'] == 'READY', 'CURRENT_GENERATION_RECOVERY_NOT_READY')
        current_ready(context)
        return row
    finally: reader.close()

def validate_exit(context, proof):
    require_tags(proof, context)
    require(proof.get('exit_confirmed') is True and proof.get('retained_handle') is True
        and proof.get('force_used') is False and set(proof.get('processes', {})) == set(ROLES), 'COHORT_EXIT_REQUIRED')
    for role in ROLES:
        value = proof['processes'][role]
        require(value.get('pid') == proof['cohort'][role]['pid']
            and value.get('birth_filetime') == proof['cohort'][role]['birth']
            and value.get('physical_exit_confirmed') is True and value.get('terminate_right') is False,
            'ALL_COHORT_EXITS_REQUIRED')
    return True

def cleanup(context):
    proof_path = context.PUBLIC / 'nexus-exit-proof.json'
    proof = read_json(proof_path); validate_exit(context, proof)
    same_cycle(proof['cohort'], cycle(context))
    service = installation(context)
    _, task = service.observe()
    require(task is not None and not task.active and task.state not in (0, 2, 4)
        and task.digest == proof['task']['digest'], 'NATIVE_TASK_INACTIVE_REQUIRED')
    absence = canonical_absence(context, 'nexus')
    result = {'kind': 'PHYSICAL_SUPERVISOR_COHORT_EXIT', 'component': 'nexus',
        'task_name': context.C['tasks']['nexus']['name'], 'task_stopped_confirmed': True,
        'owned_pid_birth_exit_confirmed': True, 'force_used': False, 'exit_proof_sha256': sha(proof_path),
        'cohort': proof['cohort'], 'canonical_absence': absence, 'runtime_work_settlement': 'NOT_ASSERTED'}
    public_save(context, 'cleanup-nexus.json', result)
    return result

def validate_cleanup(context, proof):
    require_tags(proof, context)
    require(proof.get('kind') == 'PHYSICAL_SUPERVISOR_COHORT_EXIT'
        and proof.get('task_name') == context.C['tasks']['nexus']['name']
        and proof.get('force_used') is False and proof.get('task_stopped_confirmed') is True,
        'SUPERVISOR_COHORT_PROOF_REQUIRED')
    path = context.PUBLIC / 'nexus-exit-proof.json'
    require(sha(path) == proof['exit_proof_sha256'], 'COHORT_PROOF_CHANGED')
    validate_exit(context, read_json(path))
    same_cycle(proof['cohort'], cycle(context))
    _, task = installation(context).observe()
    require(task is not None and not task.active and task.state not in (0, 2, 4), 'TASK_STILL_ACTIVE')
    canonical_absence(context, 'nexus')
    return True

def main():
    p = parser(); p.add_argument('component', choices=['nexus']); p.add_argument('operation', choices=['watch', 'cleanup'])
    p.add_argument('--watch-seconds', type=int, default=3600)
    args = p.parse_args(); context = gate(args)
    value = watch(context, args.watch_seconds) if args.operation == 'watch' else cleanup(context)
    print(json.dumps(value)); return 0

if __name__ == '__main__': raise SystemExit(main_guard(main))
