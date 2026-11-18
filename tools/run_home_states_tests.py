"""Source-only focused tests with isolated user directories and closed stdin.

The interpreter supplies existing pinned dependencies. This does not claim an
installed Nexus candidate: the bootstrap explicitly imports checkout src.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--timeout', type=float, default=1200)
    parser.add_argument('tests', nargs='+')
    args = parser.parse_args()
    assert args.label.replace('-', '').isalnum()
    assert args.timeout > 0
    tests = [(ROOT / name).resolve() for name in args.tests]
    assert all(path.is_relative_to(ROOT / 'tests') and path.exists() for path in tests)
    def pins():
        paths = {p for name in ('src', 'tests') for p in (ROOT / name).rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
        helper = ROOT / 'NEXUS_UI_R1/execution/fixtures.py'
        if helper.is_file():
            paths.add(helper)
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(paths)}
    before_pins = pins()
    owned = Path(tempfile.mkdtemp(prefix='nexus-hst-source-'))
    for name in ('cwd', 'tmp', 'user', 'appdata', 'localappdata'):
        (owned / name).mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in
           ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'NUMBER_OF_PROCESSORS', 'OS', 'SYSTEMDRIVE')}
    rtk_binary = shutil.which('rtk')
    assert rtk_binary
    env.update(PATH=os.pathsep.join((str(args.python.parent), str(Path(rtk_binary).parent),
                                    str(Path(os.environ['SYSTEMROOT']) / 'System32'))),
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
    spec = importlib.util.spec_from_file_location('home_states_owned_commands',
        ROOT / 'NEXUS_HOME_ESTADOS_R1/execution/package-hst-r3/owned_commands.py')
    owned_commands = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owned_commands)
    started = datetime.now(UTC).isoformat()
    with (owned / 'pytest.log').open('w', encoding='utf-8') as log:
        run = owned_commands.run_owned(command, root=owned, cwd=owned / 'cwd', env=env,
                                      log=log, timeout=args.timeout)
    code = run['exit_code']
    if code is None or run['timed_out'] or run['force_used'] or run['remaining_known_processes']:
        code = 124
    report_dir = ROOT / 'NEXUS_HOME_ESTADOS_R1/execution/source-tests' / args.label
    report_dir.mkdir(parents=True, exist_ok=False)
    for name in ('pytest.log', 'tests.xml'):
        if (owned / name).is_file():
            (report_dir / name).write_bytes((owned / name).read_bytes())
    report = {'mode': 'SOURCE_ONLY_NOT_INSTALLED_NEXUS', 'started_at': started,
                  'ended_at': datetime.now(UTC).isoformat(), 'command': command, 'cwd': str(owned / 'cwd'),
                  'own_root': str(owned), 'exit_code': code,
                  'original_pid': run['known_processes'][0]['pid'],
                  'process_exited': not run['remaining_known_processes'],
                  'owned_command': run, 'deadline_seconds': args.timeout,
                  'stdin': 'closed PIPE', 'provider_auth_environment_copied': False,
                  'test_files': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in tests if path.is_file()},
                  'limitations': ['No installed app/browser/real harness/human qualification.',
                                  run['observation_limit']]}
    after_pins = pins()
    report['source_and_test_drift'] = [name for name in sorted(before_pins.keys() | after_pins.keys())
                                    if before_pins.get(name) != after_pins.get(name)]
    if report['source_and_test_drift'] and code == 0:
        report['exit_code'] = code = 125
    for name, value in [('source-pins-before.json', before_pins), ('source-pins-after.json', after_pins)]:
        (report_dir / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    (report_dir / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'exit_code': code, 'report': str(report_dir), 'own_root': str(owned)}))
    print((owned / 'pytest.log').read_text('utf-8')[-4500:])
    raise SystemExit(code)


if __name__ == '__main__':
    main()
