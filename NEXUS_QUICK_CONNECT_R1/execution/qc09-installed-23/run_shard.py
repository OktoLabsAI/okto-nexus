"""Read-only installed CI runner, isolated homes and explicit origin guard.

No pip/install/product edits. The existing CI helper owns selection/hash checks;
only its pytest subprocess gets the own-temp read-only origin plugin added.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-qc-r1-package-0s9w2_3_')
PYTHON = PACKAGE / 'venv/Scripts/python.exe'
WHEEL = PACKAGE / 'artifacts/okto_nexus-0.3.6-py3-none-any.whl'
EXPECTED = '01eb1ce064f62b09630c24b5ad339814b9e46c429a7c4e7ebf7561eae23cfff6'

GUARD = '''import importlib,json,pathlib,sys
PREFIX=pathlib.Path(PREFIX_VALUE).resolve()
OUT=pathlib.Path(OUT_VALUE)
def verify(stage):
    origins={}
    for name in ('okto_nexus','nexus_connector_core','okto_nexus_connector'):
        module=importlib.import_module(name)
        origin=pathlib.Path(module.__file__).resolve()
        assert origin.is_relative_to(PREFIX) and 'site-packages' in str(origin), (name,str(origin))
        origins[name]=str(origin)
    bad=[]
    for name,module in list(sys.modules.items()):
        if any(name==p or name.startswith(p+'.') for p in origins):
            filename=getattr(module,'__file__',None)
            if filename and not pathlib.Path(filename).resolve().is_relative_to(PREFIX):
                bad.append((name,filename))
    assert not bad,bad
    (OUT / ('origins-'+stage+'.json')).write_text(json.dumps(dict(stage=stage,origins=origins,bad=bad),indent=2)+'\\n',encoding='utf-8')
def pytest_sessionstart(session):
    verify('start')
def pytest_sessionfinish(session,exitstatus):
    verify('finish')
'''


def main():
    index = int(sys.argv[1])
    assert index in (2, 3)
    assert hashlib.sha256(WHEEL.read_bytes()).hexdigest() == EXPECTED
    own = Path(tempfile.mkdtemp(prefix=f'nexus-qc09-installed-shard{index}-'))
    output = own / f'qc09-installed-shard{index}'
    output.mkdir()
    for directory in ('home', 'appdata', 'localappdata', 'tmp', 'guard'):
        (own / directory).mkdir()
    # Start from OS essentials, never carry provider/proxy/token variables.
    allowed = ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'SYSTEMDRIVE',
               'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS')
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(HOME=str(own / 'home'), USERPROFILE=str(own / 'home'),
        APPDATA=str(own / 'appdata'), LOCALAPPDATA=str(own / 'localappdata'),
        TEMP=str(own / 'tmp'), TMP=str(own / 'tmp'),
        PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    env['PATH'] = os.pathsep.join(map(str, [PACKAGE / 'venv/Scripts', Path('C:/Python313'),
        Path('C:/Windows/System32'), Path('C:/Windows'),
        Path('C:/Windows/System32/WindowsPowerShell/v1.0'),
        Path('C:/Program Files/nodejs'), Path('C:/Program Files/Git/cmd')]))
    guard = GUARD.replace('PREFIX_VALUE', repr(str(PACKAGE / 'venv'))).replace('OUT_VALUE', repr(str(output)))
    (own / 'guard/qc_installed_origin_guard.py').write_text(guard, encoding='utf-8')
    # Adapt subprocess argv only; CI helper file and input tree remain immutable.
    code = '''import importlib.util,json,pathlib,subprocess,sys
helper=pathlib.Path(HELPER_VALUE)
spec=importlib.util.spec_from_file_location('owned_ci_installed',helper)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original=subprocess.run
def run(command,*args,**kwargs):
    if isinstance(command,list) and '-m' in command and 'pytest' in command:
        before=list(command)
        pos=command.index('-m')
        assert command[pos+1]=='pytest'
        pytest_args=command[pos+2:]
        body='import sys;sys.path.insert(0,'+repr(GUARD_DIR_VALUE)+');import pytest;raise SystemExit(pytest.main('+repr(['-p','qc_installed_origin_guard',*pytest_args])+'))'
        command=[*command[:pos],'-c',body]
        pathlib.Path(OUT_VALUE,'effective-pytest-command.json').write_text(json.dumps(dict(helper_command=before,effective_command=command,cwd=kwargs.get('cwd')),indent=2),encoding='utf-8')
    if isinstance(command,list) and command and command[0]==sys.executable and '-B' not in command:
        command=[command[0],'-B',*command[1:]]
    return original(command,*args,**kwargs)
subprocess.run=run
sys.argv=ARGV_VALUE
module.main()
'''
    argv = [str(ROOT / 'tools/ci_installed.py'), 'test', '--tests', 'tests', '--shard-count', '4',
            '--shard-index', str(index), '--wheel', str(WHEEL), '--output', str(output)]
    code = (code.replace('HELPER_VALUE', repr(str(ROOT / 'tools/ci_installed.py')))
        .replace('GUARD_DIR_VALUE', repr(str(own / 'guard'))).replace('OUT_VALUE', repr(str(output)))
        .replace('ARGV_VALUE', repr(argv)))
    launcher = [str(PYTHON), '-I', '-B', '-X', 'utf8', '-u', '-c', code]
    started = time.time()
    with (output / 'stdout.txt').open('w', encoding='utf-8') as stdout, (output / 'stderr.txt').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(launcher, cwd=own, env=env, stdout=stdout, stderr=stderr)
        ready = dict(shard=index, own_root=str(own), output=str(output), child_pid=process.pid,
            wheel_sha256=EXPECTED, python=str(PYTHON), command=argv, started_at_unix=started,
            sanitized_env_names=sorted(env), path=env['PATH'], origin_guard='Own-temp pytest plugin at sessionstart/sessionfinish')
        (Path(__file__).parent / f'shard{index}-ready.json').write_text(json.dumps(ready, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(ready), flush=True)
        result = process.wait()
    final = dict(ready, exit_code=result, elapsed_seconds=time.time()-started, own_ci_child_exited=True)
    (output / 'launcher-result.json').write_text(json.dumps(final, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(shard=index, exit_code=result, output=str(output), elapsed_seconds=final['elapsed_seconds'])), flush=True)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
