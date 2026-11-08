"""Finite benign qualification, preserving all attempts in this new Temp root."""
from pathlib import Path
import hashlib
import importlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PYTHON = Path('C:/Users/jpamb/AppData/Local/Temp/m1-recovery-diagnostics-installed-xtfm5o4x/venv/Scripts/python.exe')
OLD = Path('C:/Users/jpamb/AppData/Local/Temp/m1-protected-pty-j_c21e97')
FILES = ('protected_pty.py', 'owned_job.py', 'marker_producer.py', 'marker_consumer.py',
         'test_pty_gates.py', 'qualify.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashes():
    value = {name: sha(ROOT / name) for name in FILES}
    proof = json.loads((OLD / 'dependency-proof.json').read_text())
    site = OLD / 'venv/Lib/site-packages'
    for name, pin in proof['package_payloads'].items():
        assert sha(site / name) == pin['sha256']
    assert sha(OLD / 'revision-5/protected_pty.py') == '3e9819f37d7bd04a55dc094f3e05d62f13eb8fcbf0b404abf3f2f1e9279291b1'
    assert (ROOT / 'owned_job.py').read_bytes() == (OLD / 'revision-5/owned_job.py').read_bytes()
    return {'sources': value, 'pywinpty': proof['package_payloads'], 'v5_unchanged': True,
            'pywinpty_site': str(site), 'pywinpty_version': '3.0.3'}


def write(path, value):
    path.write_bytes((json.dumps(value, indent=2) + '\n').encode())


def worker(out):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    import pytest
    helper = importlib.import_module('protected_pty')
    assert Path(helper.__file__).resolve() == ROOT / 'protected_pty.py'
    write(out / 'imports.json', {'python': sys.executable, 'base_python': sys._base_executable,
        'helper': helper.__file__, 'helper_sha256': sha(Path(helper.__file__)),
        'pytest': pytest.__file__, 'isolated': sys.flags.isolated, 'products_used': 'Only material_sink/handoff_sink synthetic functions in child; no product CLI'})
    return pytest.main(['-q', '-p', 'no:cacheprovider', '-c', str(ROOT / 'pytest.ini'),
        '--basetemp=' + str(out / 'cases'), '--junitxml=' + str(out / 'tests.xml'),
        str(ROOT / 'test_pty_gates.py')])


def main(attempt):
    out = ROOT / attempt
    out.mkdir(exist_ok=False)
    before = hashes()
    write(out / 'inputs-before.json', before)
    env = {name: os.environ[name] for name in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if name in os.environ}
    profile = out / 'profile'
    profile.mkdir()
    env.update(PATH='C:/Python313;C:/Windows/System32', HOME=str(profile), USERPROFILE=str(profile),
        APPDATA=str(profile), LOCALAPPDATA=str(profile), TEMP=str(profile), TMP=str(profile),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1')
    with (out / 'stdout.txt').open('xb') as stdout, (out / 'stderr.txt').open('xb') as stderr:
        process = subprocess.Popen([str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--worker', str(out)],
            cwd=ROOT, env=env, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        write(out / 'process.json', {'pid': process.pid, 'no_timeout_kill': True})
        print(json.dumps({'pid': process.pid, 'output': str(out)}), flush=True)
        code = process.wait()
    after = hashes()
    write(out / 'inputs-after.json', after)
    result = {'exit_code': code, 'inputs_unchanged': before == after,
              'native_product_cli_calls': 0, 'provider_calls': 0, 'real_credentials': 0,
              'native_service_actions': 0, 'scope': 'Synthetic Python/ConPTY children and pure IPC gates only'}
    write(out / 'result.json', result)
    print(json.dumps(result), flush=True)
    return code or int(before != after)


if __name__ == '__main__':
    raise SystemExit(worker(Path(sys.argv[2])) if sys.argv[1] == '--worker' else main(sys.argv[1]))
