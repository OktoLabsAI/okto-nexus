"""Reviewed finite OS-only experiment. Import has no OS task effects."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
NS = 'http://schemas.microsoft.com/windows/2004/02/mit/task'
CASES = ('manual-3', 'manual-ffffffff', 'timer-3', 'timer-ffffffff')
PREFIX = 'OktoT19-SchedulerProbe-7bg9yatu-'
PYTHON = Path('C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-39ycaumc/venv/Scripts/python.exe')
ACTION_PYTHONW = PYTHON.with_name('pythonw.exe')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(name, value):
    with (ROOT / name).open('x', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=True, sort_keys=True, indent=2)

def digest(xml):
    return hashlib.sha256(ET.canonicalize(xml_data=xml, strip_text=True).encode()).hexdigest()

def definition(case, sid, boundary):
    task = ET.Element('Task', xmlns=NS, version='1.2')
    def add(parent, name, text=None, **attrs):
        item = ET.SubElement(parent, name, attrs)
        item.text = text
        return item
    add(add(task, 'RegistrationInfo'), 'Description', 'Disposable finite OS Scheduler semantics probe; no product runtime')
    triggers = add(task, 'Triggers')
    if case.startswith('timer-'):
        trigger = add(triggers, 'TimeTrigger')
        add(trigger, 'StartBoundary', boundary)
        add(trigger, 'Enabled', 'true')
    principal = add(add(task, 'Principals'), 'Principal', id='owner')
    add(principal, 'UserId', sid)
    add(principal, 'LogonType', 'InteractiveToken')
    add(principal, 'RunLevel', 'LeastPrivilege')
    settings = add(task, 'Settings')
    for key, value in (
        ('MultipleInstancesPolicy', 'IgnoreNew'), ('DisallowStartIfOnBatteries', 'false'),
        ('StopIfGoingOnBatteries', 'false'), ('AllowHardTerminate', 'false'),
        ('StartWhenAvailable', 'true'), ('RunOnlyIfNetworkAvailable', 'false'),
        ('AllowStartOnDemand', 'true'), ('Enabled', 'true'), ('Hidden', 'false'),
        ('ExecutionTimeLimit', 'PT0S')):
        add(settings, key, value)
    restart = add(settings, 'RestartOnFailure')
    add(restart, 'Interval', 'PT1M')
    add(restart, 'Count', '1')
    action = add(add(task, 'Actions', Context='owner'), 'Exec')
    add(action, 'Command', str(ACTION_PYTHONW))
    add(action, 'Arguments', subprocess.list2cmdline(['-I', '-B', '-X', 'utf8', str(ROOT / 'action.py'), case]))
    add(action, 'WorkingDirectory', str(ROOT))
    return ET.tostring(task, encoding='unicode')

def observation(task):
    return {'state': int(task.State), 'last_run_time_raw': str(task.LastRunTime),
            'last_task_result': int(task.LastTaskResult) & 0xFFFFFFFF,
            'instances': int(task.GetInstances(0).Count), 'xml_sha256': digest(task.Xml)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-reviewed', action='store_true', required=True)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    assert sha(ROOT / 'plan.json') == args.plan_sha256, 'PLAN_CHANGED'
    plan = json.loads((ROOT / 'plan.json').read_text())
    for item in plan['pins']:
        assert sha(item['path']) == item['sha256'], 'SOURCE_CHANGED'
    assert Path(sys.executable).resolve() == PYTHON.resolve() and sys.flags.isolated, 'PYTHON_SCOPE'
    save('execution-reservation.json', {'time': time.time(), 'plan_sha256': args.plan_sha256})
    import pythoncom
    import win32com.client
    import win32api
    import win32security
    pythoncom.CoInitialize()
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
    try:
        sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
    finally:
        token.Close()
    service = win32com.client.Dispatch('Schedule.Service')
    service.Connect()
    folder = service.GetFolder('\\')
    # Exact-name absence, no task enumeration and no replacement registration.
    for case in CASES:
        try:
            folder.GetTask(PREFIX + case)
        except pythoncom.com_error as error:
            detail = error.excepinfo[5] if error.excepinfo else error.hresult
            assert (detail & 0xFFFFFFFF) == 0x80070002, 'ABSENCE_UNCONFIRMED'
        else:
            raise RuntimeError('TASK_ALREADY_EXISTS')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    created, handles, attempts, changes = {}, {}, {}, []
    failed = None
    cleanup = {}
    boundary = datetime.now(timezone.utc) + timedelta(seconds=30)
    boundary_text = boundary.isoformat(timespec='seconds')
    try:
        for case in CASES:
            (ROOT / 'attempts' / case).mkdir(parents=True, exist_ok=False)
            xml = definition(case, sid, boundary_text)
            (ROOT / f'{case}-submitted.xml').write_text(xml, encoding='utf-8')
            task = folder.RegisterTask(PREFIX + case, xml, 2, None, None, 3, None)
            native = task.Xml
            (ROOT / f'{case}-registered.xml').write_text(native, encoding='utf-8')
            created[case] = digest(native)
            save(f'{case}-registration.json', {'name': PREFIX + case, 'xml_sha256': created[case],
                                             'boundary': boundary_text, 'initial': observation(task)})
        for case in CASES[:2]:
            task = folder.GetTask(PREFIX + case)
            assert digest(task.Xml) == created[case], 'TASK_CHANGED_BEFORE_RUN'
            task.Run(None)
        deadline = time.monotonic() + max(0, boundary.timestamp() - time.time()) + 135
        previous = {}
        while time.monotonic() < deadline:
            for case in CASES:
                current = observation(folder.GetTask(PREFIX + case))
                assert current['xml_sha256'] == created[case], 'TASK_CHANGED_DURING_OBSERVATION'
                if previous.get(case) != current:
                    changes.append({'case': case, 'time': time.time(), **current})
                    previous[case] = current
                for path in sorted((ROOT / 'attempts' / case).glob('*.json')):
                    if path.name in attempts:
                        continue
                    attempt = json.loads(path.read_text())
                    attempts[path.name] = attempt
                    handle = kernel.OpenProcess(0x100000 | 0x1000, False, attempt['pid'])
                    if handle:
                        stamps = [wintypes.FILETIME() for _ in range(4)]
                        okay = kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in stamps])
                        birth = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
                        if okay and birth == attempt['birth_filetime']:
                            handles[path.name] = handle
                            attempt['identity_confirmed'] = True
                        else:
                            kernel.CloseHandle(handle)
                            attempt['identity_confirmed'] = False
                    else:
                        attempt['identity_confirmed'] = False
            for key, handle in list(handles.items()):
                if kernel.WaitForSingleObject(handle, 0) == 0:
                    code = wintypes.DWORD()
                    assert kernel.GetExitCodeProcess(handle, ctypes.byref(code)), 'EXIT_CODE_UNCONFIRMED'
                    attempts[key].update(physical_exit=True, actual_exit_code=code.value, exit_observed_at=time.time())
                    kernel.CloseHandle(handle)
                    del handles[key]
            time.sleep(0.25)
    except Exception as error:
        failed = type(error).__name__ + ':' + str(error)
    finally:
        # Delete only unchanged, already inactive own definitions; never Stop or force.
        for case, expected in created.items():
            try:
                task = folder.GetTask(PREFIX + case)
                final = observation(task)
                assert final['xml_sha256'] == expected, 'TASK_CHANGED_BEFORE_CLEANUP'
                assert final['state'] == 3 and final['instances'] == 0, 'TASK_NOT_INACTIVE'
                folder.DeleteTask(PREFIX + case, 0)
                try:
                    folder.GetTask(PREFIX + case)
                except pythoncom.com_error as error:
                    detail = error.excepinfo[5] if error.excepinfo else error.hresult
                    assert (detail & 0xFFFFFFFF) == 0x80070002, 'CLEANUP_ABSENCE_UNKNOWN'
                else:
                    raise RuntimeError('TASK_STILL_PRESENT')
                cleanup[case] = {'absent': True, 'final': final}
            except Exception as error:
                cleanup[case] = {'absent': False, 'error': type(error).__name__ + ':' + str(error)}
        for handle in handles.values():
            kernel.CloseHandle(handle)
        if failed is None:
            for case in CASES:
                selected = [a for a in attempts.values() if a['case'] == case]
                if not (1 <= len(selected) <= 2) or any(a['budget_guard'] for a in selected):
                    failed = 'ATTEMPT_COUNT_UNCONFIRMED'
                elif any(not a.get('physical_exit') or a.get('actual_exit_code') != a['intended_exit_code'] for a in selected):
                    failed = 'ATTEMPT_PHYSICAL_EXIT_UNCONFIRMED'
        save('result.json', {'failure': failed, 'attempts': list(attempts.values()),
                             'native_changes': changes, 'cleanup': cleanup,
                             'force_used': False, 'product_services_used': False,
                             'limitations': 'Observed matrix only; no general proof of all Scheduler restart causes.'})
        pythoncom.CoUninitialize()
    return 1 if failed or len(cleanup) != 4 or not all(v['absent'] for v in cleanup.values()) else 0

if __name__ == '__main__':
    raise SystemExit(main())
