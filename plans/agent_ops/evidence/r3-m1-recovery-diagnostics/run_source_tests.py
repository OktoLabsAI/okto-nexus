"""Bounded source-only qualification; no package installation or service CLI."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
PYTHON = Path('C:/Users/jpamb/AppData/Local/Temp/m1-check-recovery-inopit5p/venv/Scripts/python.exe')
PRODUCT = [
    'src/okto_nexus/adapters/outbound/sqlite/diagnostics.py',
    'src/okto_nexus/adapters/outbound/sqlite/write_gate.py',
    'src/okto_nexus/bootstrap/embedded_agent_recovery.py',
]
TESTS = [
    'tests/test_embedded_recovery_diagnostics.py',
    'tests/test_sqlite_writer_fairness.py',
    'tests/test_import_boundary.py',
    'tests/execution_r4/test_recovery_diagnostic_contention.py',
]


def hashes():
    return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest()
            for name in PRODUCT + TESTS}


def write(name, document):
    (ROOT / name).write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')


def worker():
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(REPO / 'src'), str(REPO / 'tests'), str(REPO / 'tests/execution_r4')]
    modules = {}
    for name in [
        'okto_nexus.bootstrap.embedded_agent_recovery',
        'okto_nexus.adapters.outbound.sqlite.diagnostics',
        'okto_nexus.adapters.outbound.sqlite.write_gate',
    ]:
        path = Path(importlib.import_module(name).__file__).resolve()
        assert path.is_relative_to(REPO / 'src'), (name, str(path))
        modules[name] = str(path)
    import nexus_connector_core
    import pytest
    write('imports.json', {'executable': sys.executable, 'base_executable': sys._base_executable,
        'prefix': sys.prefix, 'version': sys.version, 'source_modules': modules,
        'core_module': nexus_connector_core.__file__, 'pytest_module': pytest.__file__,
        'isolated': sys.flags.isolated, 'dont_write_bytecode': sys.dont_write_bytecode})
    return pytest.main(['-q', '-p', 'no:cacheprovider', '-o', 'pythonpath=',
        '--basetemp=' + str(ROOT / 'cases'), '--junitxml=' + str(ROOT / 'source.xml'),
        *[str(REPO / name) for name in TESTS]])


def launch():
    before = hashes()
    write('input-hashes-before.json', before)
    env = {name: os.environ[name] for name in ('SYSTEMROOT', 'WINDIR', 'COMSPEC') if name in os.environ}
    profile = ROOT / 'profile'
    for name in ('home', 'roaming', 'local', 'temp'):
        (profile / name).mkdir(parents=True, exist_ok=True)
    env.update(HOME=str(profile / 'home'), USERPROFILE=str(profile / 'home'),
        APPDATA=str(profile / 'roaming'), LOCALAPPDATA=str(profile / 'local'),
        TEMP=str(profile / 'temp'), TMP=str(profile / 'temp'),
        PATH=str(PYTHON.parent) + ';C:/Windows/System32;C:/Windows',
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1',
        PYTHONNOUSERSITE='1', NO_PROXY='*')
    write('environment.json', env)
    started = time.monotonic()
    with (ROOT / 'source.stdout.txt').open('w', encoding='utf-8') as out, (ROOT / 'source.stderr.txt').open('w', encoding='utf-8') as err:
        child = subprocess.Popen([str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--worker'],
            cwd=ROOT, env=env, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
        write('process.json', {'pid': child.pid, 'interpreter': str(PYTHON), 'state': 'running',
            'no_timeout_kill': True})
        print(json.dumps({'pid': child.pid, 'root': str(ROOT)}), flush=True)
        code = child.wait()
    after = hashes()
    write('input-hashes-after.json', after)
    result = {'exit_code': code, 'elapsed_seconds': time.monotonic() - started,
              'input_hashes_unchanged': before == after,
              'selection': TESTS, 'no_installation': True, 'no_provider': True,
              'scope': 'source tests, SQLite temporary databases and synthetic embedded peer'}
    write('result.json', result)
    print(json.dumps(result), flush=True)
    return code or int(before != after)


if __name__ == '__main__':
    raise SystemExit(worker() if sys.argv[1:] == ['--worker'] else launch())
