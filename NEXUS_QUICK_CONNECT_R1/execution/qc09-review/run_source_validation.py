"""Finite installed-product tests over disposable fixture-only changes."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
root=Path(json.loads((HERE/'source-validation-allocation.json').read_text())['root']).resolve()
package=Path(r'C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1').resolve()
python=package/'venv/Scripts/python.exe'
assert not (root/'after/src').exists()
rtk=shutil.which('rtk')
assert rtk and os.name=='nt'
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
kernel.OpenProcess.restype=wintypes.HANDLE
kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
kernel.GetProcessTimes.restype=wintypes.BOOL
kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
kernel.WaitForSingleObject.restype=wintypes.DWORD
kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
kernel.TerminateProcess.restype=wintypes.BOOL
kernel.CloseHandle.argtypes=[wintypes.HANDLE]


class Owned:
    def __init__(self,pid,parent=None):
        self.pid,self.parent=pid,parent
        self.handle=kernel.OpenProcess(0x1000|0x100000|0x1,False,pid)
        if not self.handle:
            raise ProcessLookupError(pid)
        times=[wintypes.FILETIME() for _ in range(4)]
        assert kernel.GetProcessTimes(self.handle,*map(ctypes.byref,times))
        self.birth=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime

    def alive(self):
        return kernel.WaitForSingleObject(self.handle,0)==258

    def terminate(self):
        if self.alive():
            assert kernel.TerminateProcess(self.handle,124)

    def facts(self):
        return dict(pid=self.pid,parent_pid=self.parent,birth_filetime=self.birth,alive=self.alive())


def payload():
    site=package/'venv/Lib/site-packages'
    return {str(p.relative_to(site)):hashlib.sha256(p.read_bytes()).hexdigest()
        for module in ('okto_nexus','nexus_connector_core','okto_nexus_connector')
        for p in (site/module).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}


plugin='''
import importlib.util,json,pathlib,re,sys
import pytest
ROOT=pathlib.Path(__file__).resolve().parents[1]
PREFIX=pathlib.Path(%r).resolve()
OUT=pathlib.Path(__import__('os').environ['QC_DERIVATIVE_OUTPUT'])

def pytest_sessionstart(session):
    origins={name:importlib.util.find_spec(name).origin for name in ('okto_nexus','nexus_connector_core','okto_nexus_connector')}
    assert pathlib.Path(origins['okto_nexus']).resolve().is_relative_to(pathlib.Path('D:\\Projetos\\Techridy\\okto_labs_okto_nexus\\src')),origins
    assert all(pathlib.Path(value).resolve().is_relative_to(PREFIX) for name,value in origins.items() if name!='okto_nexus'),origins
    assert not (ROOT/'src').exists()
    (OUT/'origins.json').write_text(json.dumps(dict(origins=origins,prefix=sys.prefix,sys_path=sys.path),indent=2))

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    report=outcome.get_result()
    record=dict(nodeid=report.nodeid,when=report.when,outcome=report.outcome,duration=report.duration)
    if report.failed:
        text=report.longreprtext
        text=re.sub(r'(?:nxs_|nxsept_|nxc4_|nxt4_)[A-Za-z0-9_-]+','<ephemeral-token-redacted>',text)
        record['failure']=text
        if report.when=='call':
            (OUT/'failed-call.json').write_text(json.dumps(record,indent=2))
    with (OUT/'reports.jsonl').open('a') as f:
        f.write(json.dumps(record)+'\\n')
    print('IMMEDIATE_REPORT '+json.dumps(record),flush=True)
''' % str(package/'venv')
(root/'release_plugin.py').write_text(plugin,encoding='utf-8')
spec=importlib.util.spec_from_file_location('qc09_own_environment',HERE.parent/'qc08-package/package.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
before=payload()
reports=[]
nodes=[('compatibility-50', 'tests/quick_connect/test_entry_compatibility.py'), ('canonical-shortcut', 'tests/execution_r4/test_connection_catalog.py::test_cli_existing_canonical_without_profile_creates_only_shortcut'), ('single-harness', 'tests/execution_r4/test_terminal_multi_harness.py::test_single_observed_harness_needs_no_profile_and_existing_connection_offers_all_intents'), ('two-harnesses', 'tests/execution_r4/test_terminal_multi_harness.py::test_two_distinct_harnesses_share_project_keep_custom_a_and_recover_b_finish')]
for label,node in nodes:
    out=root/label
    out.mkdir(exist_ok=False)
    env=builder.environment(out)
    env['PATH']=str(out/'empty-path')
    (out/'empty-path').mkdir()
    env['QC_DERIVATIVE_OUTPUT']=str(out)
    command=[rtk,'proxy',str(python),'-I','-B','-c',"import sys,runpy;sys.path[:0]="+repr([str(REPO/'src'),str(root)])+";runpy.run_module('pytest',run_name='__main__')",'-p','release_plugin','-c',str(root/'pytest.ini'),
        '--rootdir='+str(REPO),'--confcutdir='+str(REPO/'tests'),str(REPO/node),
        '-v','-s','--tb=short','-o','faulthandler_timeout=10','--junitxml='+str(out/'junit.xml')]
    record=dict(label=label,argv=command,cwd=str(root),deadline_seconds=60,
                started_at=datetime.now(timezone.utc).isoformat(),signals=[])
    known={}
    with (out/'raw.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        known[process.pid]=Owned(process.pid)
        deadline=time.monotonic()+60
        failed_at=None
        signaled_at=None
        hard_at=None
        while process.poll() is None:
            alive=[pid for pid,item in known.items() if item.alive()]
            if alive:
                query=' OR '.join('ParentProcessId='+str(pid) for pid in alive)
                ps='Get-CimInstance Win32_Process -Filter "'+query+'" | Select-Object ProcessId,ParentProcessId | ConvertTo-Json'
                result=subprocess.run([rtk,'proxy','C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe',
                    '-NoProfile','-Command',ps],cwd=out,env=env,capture_output=True,text=True,timeout=8)
                if result.stdout.strip():
                    children=json.loads(result.stdout)
                    for child in children if isinstance(children,list) else [children]:
                        parent=known.get(child['ParentProcessId'])
                        if parent is not None and parent.alive() and child['ProcessId'] not in known:
                            try:
                                known[child['ProcessId']]=Owned(child['ProcessId'],child['ParentProcessId'])
                            except ProcessLookupError:
                                pass
            now=time.monotonic()
            if (out/'failed-call.json').exists() and failed_at is None:
                failed_at=now
            due=now>=deadline or failed_at is not None and now-failed_at>=15
            if due and signaled_at is None:
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                    record['signals'].append('CTRL_BREAK to this own new process group')
                except OSError as error:
                    record['signals'].append('CTRL_BREAK unavailable: '+type(error).__name__)
                signaled_at=now
            if signaled_at is not None and now-signaled_at>=5 and hard_at is None:
                record['before_hard_creation_proofs']=[item.facts() for item in known.values()]
                for item in reversed(list(known.values())):
                    item.terminate()
                record['signals'].append('TerminateProcess only retained exact own process handles after birth/parent proof')
                hard_at=now
            if hard_at is not None and now-hard_at>10:
                raise RuntimeError('Owned derivative process did not exit; retain handles and data for audit.')
            time.sleep(.1)
        process.wait(timeout=1)
    record['exit_code']=process.returncode
    record['processes_after']=[item.facts() for item in known.values()]
    assert all(not item['alive'] for item in record['processes_after'])
    for item in known.values():
        kernel.CloseHandle(item.handle)
    record['ended_at']=datetime.now(timezone.utc).isoformat()
    (out/'runner.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    reports.append(record)
    print(json.dumps(dict(label=label,exit_code=process.returncode,signals=record['signals'])),flush=True)
after=payload()
assert before==after
source=json.loads((root/'source-pins.json').read_text())
changed=[name for name,pin in source.items() if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=pin]
assert not changed,changed
(root/'result.json').write_text(json.dumps(dict(cases=reports,payload_files=len(before),payload_drift=[],
    repository_input_drift=changed,app_source_present=True, qualification='SOURCE_ONLY_PR27_DEPENDENCIES'),indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(root=str(root),cases=[dict(label=r['label'],exit_code=r['exit_code']) for r in reports],
                     payload_files=len(before),payload_drift=[])),flush=True)
