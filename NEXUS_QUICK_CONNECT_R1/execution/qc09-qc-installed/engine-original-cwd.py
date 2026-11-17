"""Exact collected-node remainder; bounded watchdog, never edits product/tests.

Original interrupted runs remain immutable antecedents. Each derivative wave
uses a fresh own home; failed/hung nodes never become PASS by exclusion.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

import psutil
from run_shard import ROOT, PACKAGE, PYTHON, GUARD

HERE = Path(__file__).resolve().parent
PLUGIN = '''import json,pathlib,pytest,time
OUT=pathlib.Path(OUT_VALUE)
def pytest_collection_finish(session):
    (OUT/'all-nodeids.json').write_text(json.dumps([i.nodeid for i in session.items],indent=2),encoding='utf-8')
def pytest_runtest_logstart(nodeid,location):
    (OUT/'progress.json').write_text(json.dumps(dict(nodeid=nodeid,phase='start',at=time.time())),encoding='utf-8')
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    value=yield
    r=value.get_result()
    row=dict(nodeid=r.nodeid,phase=r.when,outcome=r.outcome,at=time.time())
    (OUT/'progress.json').write_text(json.dumps(row),encoding='utf-8')
    with (OUT/'reports.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(row)+'\\n')
    if r.failed:
        with (OUT/'failures.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(row,longrepr=r.longreprtext))+'\\n')
'''


def environment(own):
    own.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k.upper() in (
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'SYSTEMDRIVE', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS')}
    for name in ('home', 'appdata', 'localappdata', 'tmp', 'guard', 'output'):
        (own / name).mkdir()
    env.update(HOME=str(own / 'home'), USERPROFILE=str(own / 'home'), APPDATA=str(own / 'appdata'),
        LOCALAPPDATA=str(own / 'localappdata'), TEMP=str(own / 'tmp'), TMP=str(own / 'tmp'),
        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
        PATH=os.pathsep.join(map(str, [PACKAGE / 'venv/Scripts', Path('C:/Python313'), Path('C:/Windows/System32'),
            Path('C:/Windows'), Path('C:/Windows/System32/WindowsPowerShell/v1.0'), Path('C:/Program Files/nodejs'), Path('C:/Program Files/Git/cmd')])))
    return env


def execute(own, selectors, *, collect=False):
    env = environment(own)
    out = own / 'output'
    (own / 'guard/qc_installed_origin_guard.py').write_text(GUARD.replace('PREFIX_VALUE', repr(str(PACKAGE / 'venv'))).replace('OUT_VALUE', repr(str(out))), encoding='utf-8')
    (own / 'guard/qc_wave_report.py').write_text(PLUGIN.replace('OUT_VALUE', repr(str(out))), encoding='utf-8')
    config = own / 'pytest.ini'
    config.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n', encoding='utf-8')
    args = ['-p', 'qc_installed_origin_guard', '-p', 'qc_wave_report', '-c', str(config),
        '--rootdir=' + str(ROOT), '--confcutdir=' + str(ROOT / 'tests'), *[str(ROOT / node) for node in selectors],
        '-q' if collect else '-v', '--tb=short', '--junitxml=' + str(out / 'tests.xml')]
    if collect:
        args.append('--collect-only')
    argsfile = own / 'pytest-args.json'
    argsfile.write_text(json.dumps(args), encoding='utf-8')
    code = ('import sys,json,pathlib;sys.path.insert(0,' + repr(str(own / 'guard')) + ');'
        'import pytest;raise SystemExit(pytest.main(json.loads(pathlib.Path(' + repr(str(argsfile)) + ').read_text())))')
    argv = [str(PYTHON), '-I', '-B', '-X', 'utf8', '-u', '-c', code]
    tracked, phases = {}, []
    with (out / 'stdout.txt').open('w', encoding='utf-8') as stdout, (out / 'stderr.txt').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(argv, cwd=own, env=env, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        started = last_progress = time.time()
        interrupted = dumped = False
        while process.poll() is None:
            try:
                family = [psutil.Process(process.pid), *psutil.Process(process.pid).children(recursive=True)]
            except psutil.NoSuchProcess:
                family = []
            for child in family:
                try:
                    tracked[child.pid] = dict(pid=child.pid, ppid=child.ppid(), create_time=child.create_time(), exe=child.exe())
                except psutil.NoSuchProcess:
                    pass
            progress = out / 'progress.json'
            if progress.exists():
                last_progress = max(last_progress, progress.stat().st_mtime)
            idle = time.time() - last_progress
            if idle >= 110 and not dumped:
                dumped = True
                for child in family:
                    if child.pid == process.pid:
                        continue
                    try:
                        result = subprocess.run(['C:/Users/jpamb/AppData/Roaming/Python/Python313/Scripts/py-spy.exe',
                            'dump', '--pid', str(child.pid)], capture_output=True, text=True, encoding='utf-8', timeout=3)
                        (out / f'stall-stack-{child.pid}.txt').write_text('\n'.join(line for line in result.stdout.splitlines()
                            if not line.startswith('Process '))+'\n', encoding='utf-8')
                    except (psutil.NoSuchProcess, subprocess.TimeoutExpired):
                        pass
            if idle >= 115 and not interrupted:
                interrupted = True
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                    phases.append('Dedicated own-group interrupt at115s without progress')
                except OSError:
                    phases.append('Dedicated own-group interrupt unavailable')
            if idle >= 120:
                phases.append('120s phase watchdog: verified own-tree containment')
                for pid, identity in reversed(list(tracked.items())):
                    try:
                        child = psutil.Process(pid)
                        if child.create_time() == identity['create_time']:
                            child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                break
            time.sleep(.25)
        code = process.wait(timeout=10)
    physical = {}
    for pid, identity in tracked.items():
        try:
            child = psutil.Process(pid)
            if child.create_time() == identity['create_time']:
                child.wait(timeout=5)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass
        physical[str(pid)] = not psutil.pid_exists(pid) or psutil.Process(pid).create_time() != identity['create_time']
    result = dict(command=argv, pytest_args=args, exit_code=code, elapsed_seconds=time.time()-started,
        phases=phases, tracked_processes=list(tracked.values()), physically_exited=physical)
    (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return out, result


def main():
    index = int(sys.argv[1])
    assert index in (0, 1)
    run = len(sys.argv) > 2 and sys.argv[2] == '--run'
    ready = json.loads((HERE / f'shard{index}-ready.json').read_text())
    original = Path(ready['output'])
    campaign = json.loads((original / 'campaign.json').read_text())
    own = Path(tempfile.mkdtemp(prefix=f'nexus-qc09-remainder{index}-'))
    out, collection = execute(own / 'collection', campaign['tests'], collect=True)
    assert collection['exit_code'] == 0, collection
    nodes = json.loads((out / 'all-nodeids.json').read_text())
    finished = {}
    for line in (original / 'stdout.txt').read_text(encoding='utf-8').splitlines():
        match = re.match(r'(.+::.+?) (PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS) \[', line)
        if not match:
            continue
        file, rest = match[1].split('::', 1)
        relative = Path(file).relative_to(ROOT).as_posix() + '::' + rest
        finished[relative] = match[2]
    assert set(finished) <= set(nodes), set(finished) - set(nodes)
    remaining = [node for node in nodes if node not in finished]
    manifest = dict(shard=index, own_root=str(own), original_campaign=str(original / 'campaign.json'),
        original_status='INTERRUPTED_HUNG_TEST', selected_files=campaign['tests'], collected_total=len(nodes),
        completed_original=finished, remaining=remaining, remaining_count=len(remaining), collection=collection,
        policy='No node silently removed by whole-file exclusion; known failures remain failures, original SKIPs remain SKIP; installed pytest parent does not prove fixture child origins.')
    plan = HERE / f'remainder{index}-plan.json'
    plan.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(shard=index, plan=str(plan), collected=len(nodes), completed=len(finished), remaining=len(remaining), own_root=str(own))), flush=True)
    if not run:
        return 0
    spec = importlib.util.spec_from_file_location('input_helper', ROOT / 'tools/ci_installed.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    before = helper.input_hashes()
    waves = []
    for number in range(1, 9):
        if not remaining:
            break
        wave, result = execute(own / f'wave{number}', remaining)
        reports = [json.loads(line) for line in (wave / 'reports.jsonl').read_text().splitlines()] if (wave / 'reports.jsonl').exists() else []
        complete = {r['nodeid'] for r in reports if r['phase'] == 'teardown'}
        hung = None
        if result['phases']:
            progress = wave / 'progress.json'
            hung = json.loads(progress.read_text()) if progress.exists() else None
            if hung:
                complete.add(hung['nodeid'])
        record = dict(wave=number, output=str(wave), result=result, completed_count=len(complete), interrupted_node=hung)
        waves.append(record)
        remaining = [node for node in remaining if node not in complete]
        after = helper.input_hashes()
        changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        summary = dict(shard=index, waves=waves, still_not_run=remaining, changed_inputs=changed,
            status='INPUTS_CHANGED' if changed else 'INCOMPLETE' if remaining else 'EXECUTED_WITH_RECORDED_FAILURES_OR_SKIPS')
        (HERE / f'remainder{index}-result.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(dict(shard=index, wave=number, exit_code=result['exit_code'], interrupted_node=hung,
            completed=len(complete), remaining=len(remaining), changed_inputs=changed)), flush=True)
        if changed or not complete:
            break
    return 0 if not remaining else 2


if __name__ == '__main__':
    raise SystemExit(main())
