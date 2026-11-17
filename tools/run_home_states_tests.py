"""Source-only focused tests with isolated user directories and closed stdin.

The interpreter supplies existing pinned dependencies. This does not claim an
installed Nexus candidate: the bootstrap explicitly imports checkout src.
"""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('tests', nargs='+')
    args = parser.parse_args()
    assert args.label.replace('-', '').isalnum()
    tests = [(ROOT / name).resolve() for name in args.tests]
    assert all(path.is_relative_to(ROOT / 'tests') and path.exists() for path in tests)
    pinned = set(ROOT.joinpath('src').rglob('*.py'))
    for path in tests:
        pinned.update(path.rglob('*.py') if path.is_dir() else [path])
    pinned.update((ROOT / 'tests').glob('conftest.py'))
    def pins():
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(pinned)}
    before_pins = pins()
    owned = Path(tempfile.mkdtemp(prefix='nexus-hst-source-'))
    for name in ('cwd', 'tmp', 'user', 'appdata', 'localappdata'):
        (owned / name).mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in
           ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'NUMBER_OF_PROCESSORS', 'OS', 'SYSTEMDRIVE')}
    env.update(PATH=str(args.python.parent) + os.pathsep + str(Path(os.environ['SYSTEMROOT']) / 'System32'),
               USERPROFILE=str(owned / 'user'), HOME=str(owned / 'user'), APPDATA=str(owned / 'appdata'),
               LOCALAPPDATA=str(owned / 'localappdata'), TMP=str(owned / 'tmp'), TEMP=str(owned / 'tmp'),
               PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    ini = owned / 'pytest.ini'
    ini.write_text('[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n', encoding='utf-8')
    pytest_args = ['-p', 'pytest_asyncio.plugin', '-p', 'no:cacheprovider', '-c', str(ini),
                   '--rootdir=' + str(ROOT), '--confcutdir=' + str(ROOT), '--basetemp=' + str(owned / 'cases'),
                   '-q', '--tb=short', '--junitxml=' + str(owned / 'tests.xml'), *map(str, tests)]
    bootstrap = ('import sys;sys.path.insert(0,' + repr(str(ROOT)) + ');sys.path.insert(0,' + repr(str(ROOT / 'src')) +
                 ');import pytest;raise SystemExit(pytest.main(' + repr(pytest_args) + '))')
    command = [str(args.python), '-I', '-B', '-X', 'utf8', '-c', bootstrap]
    started = datetime.now(UTC).isoformat()
    with (owned / 'pytest.log').open('w', encoding='utf-8') as log:
        child = subprocess.Popen(command, cwd=owned / 'cwd', env=env, stdin=subprocess.PIPE,
                                 stdout=log, stderr=subprocess.STDOUT)
        child.stdin.close()
        code = child.wait()
    report_dir = ROOT / 'NEXUS_HOME_ESTADOS_R1/execution/source-tests' / args.label
    report_dir.mkdir(parents=True, exist_ok=False)
    for name in ('pytest.log', 'tests.xml'):
        if (owned / name).is_file():
            (report_dir / name).write_bytes((owned / name).read_bytes())
    report = {'mode': 'SOURCE_ONLY_NOT_INSTALLED_NEXUS', 'started_at': started,
                  'ended_at': datetime.now(UTC).isoformat(), 'command': command, 'cwd': str(owned / 'cwd'),
                  'own_root': str(owned), 'exit_code': code, 'original_pid': child.pid, 'process_exited': child.poll() is not None,
                  'stdin': 'closed PIPE', 'provider_auth_environment_copied': False,
                  'test_files': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in tests if path.is_file()},
                  'limitations': ['No installed app/browser/real harness/human qualification.',
                               'No automatic process containment; only this test process exit is claimed.']}
    after_pins = pins()
    report['source_and_test_drift'] = [name for name in sorted(before_pins)
                                    if before_pins[name] != after_pins[name]]
    for name, value in [('source-pins-before.json', before_pins), ('source-pins-after.json', after_pins)]:
        (report_dir / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    (report_dir / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'exit_code': code, 'report': str(report_dir), 'own_root': str(owned)}))
    print((owned / 'pytest.log').read_text('utf-8')[-4500:])
    raise SystemExit(code)


if __name__ == '__main__':
    main()
