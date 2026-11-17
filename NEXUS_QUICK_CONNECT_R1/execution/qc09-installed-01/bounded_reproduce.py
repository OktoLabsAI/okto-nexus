"""Exact own-node diagnostic, at most30s before verified subtree containment."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

import psutil
from run_shard import ROOT, PACKAGE, WHEEL, EXPECTED, GUARD

HERE = Path(__file__).resolve().parent
NODE = 'tests/execution_r4/test_canonical_handoff_recovery.py::test_late_structured_output_cannot_complete_reclaimed_work'
REPORT_PLUGIN = '''import json,pathlib,pytest
OUT=pathlib.Path(OUT_VALUE)
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    result=yield
    report=result.get_result()
    text=report.longreprtext if report.failed else ''
    (OUT / ('report-'+report.when+'.json')).write_text(json.dumps(dict(nodeid=report.nodeid,when=report.when,outcome=report.outcome,longrepr=text),indent=2)+'\\n',encoding='utf-8')
    if report.failed:
        (OUT / ('failure-'+report.when+'.txt')).write_text(text,encoding='utf-8')
'''


def main():
    label = sys.argv[1]
    assert label in ('candidate', 'baseline')
    prefix = PACKAGE / 'venv' if label == 'candidate' else Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui-r3-harness-pr27-gsg_twh1/venv')
    assert hashlib.sha256(WHEEL.read_bytes()).hexdigest() == EXPECTED
    own = Path(tempfile.mkdtemp(prefix='nexus-qc09-bounded-' + label + '-'))
    out = own / 'output'
    for name in ('output', 'home', 'appdata', 'localappdata', 'tmp', 'guard'):
        (own / name).mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in (
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'SYSTEMDRIVE', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS')}
    env.update(HOME=str(own / 'home'), USERPROFILE=str(own / 'home'), APPDATA=str(own / 'appdata'),
        LOCALAPPDATA=str(own / 'localappdata'), TEMP=str(own / 'tmp'), TMP=str(own / 'tmp'),
        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
        PATH=os.pathsep.join(map(str, [prefix / 'Scripts', Path('C:/Python313'), Path('C:/Windows/System32'),
            Path('C:/Windows'), Path('C:/Windows/System32/WindowsPowerShell/v1.0'), Path('C:/Program Files/nodejs'), Path('C:/Program Files/Git/cmd')])))
    (own / 'guard/qc_installed_origin_guard.py').write_text(GUARD.replace('PREFIX_VALUE', repr(str(prefix))).replace('OUT_VALUE', repr(str(out))), encoding='utf-8')
    (own / 'guard/qc_report_guard.py').write_text(REPORT_PLUGIN.replace('OUT_VALUE', repr(str(out))), encoding='utf-8')
    config = own / 'pytest.ini'
    config.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n', encoding='utf-8')
    args = ['-p', 'qc_installed_origin_guard', '-p', 'qc_report_guard', '-c', str(config), '--rootdir=' + str(ROOT),
        '--confcutdir=' + str(ROOT / 'tests'), str(ROOT / NODE), '-vv', '--tb=long', '--junitxml=' + str(out / 'tests.xml')]
    code = ('import sys,importlib.metadata;sys.path.insert(0,' + repr(str(own / 'guard')) + ');'
        'print("NEXUS_VERSION",importlib.metadata.version("okto-nexus"),flush=True);'
        'import pytest;raise SystemExit(pytest.main(' + repr(args) + '))')
    argv = [str(prefix / 'Scripts/python.exe'), '-I', '-B', '-X', 'utf8', '-u', '-c', code]
    started = time.monotonic()
    tracked = {}
    phases = []
    with (out / 'stdout.txt').open('w', encoding='utf-8') as stdout, (out / 'stderr.txt').open('w', encoding='utf-8') as stderr:
        child = subprocess.Popen(argv, cwd=own, env=env, stdout=stdout, stderr=stderr,
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        ready = dict(label=label, own_root=str(own), output=str(out), command=argv, child_pid=child.pid,
            created_new_process_group=True, timeout_seconds=30)
        (HERE / f'bounded-{label}-ready.json').write_text(json.dumps(ready, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(ready), flush=True)
        dumped = interrupted = False
        while child.poll() is None:
            try:
                family = [psutil.Process(child.pid), *psutil.Process(child.pid).children(recursive=True)]
            except psutil.NoSuchProcess:
                family = []
            for process in family:
                try:
                    tracked[process.pid] = dict(pid=process.pid, ppid=process.ppid(), create_time=process.create_time(), exe=process.exe())
                except psutil.NoSuchProcess:
                    pass
            age = time.monotonic() - started
            if age >= 20 and not dumped:
                dumped = True
                for process in family:
                    try:
                        if 'pytest.main' in ' '.join(process.cmdline()) and process.pid != child.pid:
                            result = subprocess.run(['C:/Users/jpamb/AppData/Roaming/Python/Python313/Scripts/py-spy.exe',
                                'dump', '--pid', str(process.pid)], capture_output=True, text=True, encoding='utf-8', timeout=3)
                            (out / f'stack-{process.pid}.txt').write_text('\n'.join(line for line in result.stdout.splitlines()
                                if not line.startswith('Process '))+'\n', encoding='utf-8')
                    except (psutil.NoSuchProcess, subprocess.TimeoutExpired):
                        pass
            if age >= 25 and not interrupted:
                interrupted = True
                try:
                    child.send_signal(signal.CTRL_BREAK_EVENT)
                    phases.append('CTRL_BREAK sent only to dedicated own process group at25s')
                except OSError as error:
                    phases.append('Dedicated group interrupt unavailable: ' + type(error).__name__)
            if age >= 30:
                phases.append('30s timeout reached; terminate only tracked creation-time-verified own descendants')
                for pid, identity in reversed(list(tracked.items())):
                    try:
                        process = psutil.Process(pid)
                        if process.create_time() == identity['create_time']:
                            process.terminate()
                    except psutil.NoSuchProcess:
                        pass
                break
            time.sleep(.1)
        result = child.wait(timeout=5)
    states = {}
    for pid, identity in tracked.items():
        try:
            process = psutil.Process(pid)
            if process.create_time() == identity['create_time']:
                process.wait(timeout=5)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass
        states[str(pid)] = not psutil.pid_exists(pid) or psutil.Process(pid).create_time() != identity['create_time']
    final = dict(ready, exit_code=result, elapsed_seconds=time.monotonic()-started, phases=phases,
        tracked_processes=list(tracked.values()), physically_exited=states)
    (out / 'result.json').write_text(json.dumps(final, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(label=label, exit_code=result, phases=phases, physically_exited=states)), flush=True)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
