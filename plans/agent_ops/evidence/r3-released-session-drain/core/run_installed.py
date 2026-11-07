import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).parent
SNAPSHOT = HERE / 'candidate' / 'snapshot'
VENV = Path('C:/Users/jpamb/AppData/Local/Temp/m1-drain-hosts-n7pm3omg/venv')
PYTHON = VENV / 'Scripts' / 'python.exe'
package = VENV / 'Lib' / 'site-packages'
destination = HERE / 'installed-final'
destination.mkdir(exist_ok=False)
home = destination / 'home'
home.mkdir()
tests = json.loads((HERE / 'source-final' / 'result.json').read_text())['tests']
proof = json.loads((HERE / 'candidate' / 'package-proof.json').read_text())
wheel = Path(proof['wheel'])
assert hashlib.sha256(wheel.read_bytes()).hexdigest() == proof['wheel_sha256']
with zipfile.ZipFile(wheel) as archive:
    expected = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()
                if name.startswith('nexus_connector_core/') and not name.endswith('/')}
def package_hashes():
    return {name: hashlib.sha256((package / name).read_bytes()).hexdigest() for name in expected}
assert package_hashes() == expected
def test_hashes():
    return {str(path.relative_to(SNAPSHOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (SNAPSHOT / 'tests').rglob('*') if path.is_file()
            and '__pycache__' not in path.parts}
test_before = test_hashes()
environment = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
environment.update(PATH=str(PYTHON.parent) + ';' + str(Path(environment['SYSTEMROOT']) / 'System32'),
                   HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home),
                   TEMP=str(home), TMP=str(home), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1')
child = destination / 'run.py'
child.write_text('''import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'tests'))
import nexus_connector_core, pytest
path = Path(nexus_connector_core.__file__).resolve()
assert path.is_relative_to(Path(sys.prefix).resolve()), path
assert not any(Path(entry).resolve().name == 'src' for entry in sys.path if entry)
Path(sys.argv[2]).write_text(json.dumps({'core_import': str(path), 'python': sys.executable,
    'sys_path': sys.path}, indent=2))
raise SystemExit(pytest.main(sys.argv[3:]))
''', encoding='utf-8')
command = [str(PYTHON), '-I', str(child), str(SNAPSHOT), str(destination / 'imports.json'),
           '-p', 'pytest_asyncio.plugin', '-q', '--tb=short', '-o', 'cache_dir=' + str(destination / 'cache'),
           '--basetemp=' + str(destination / 'pytest'), '--junitxml=' + str(destination / 'tests.xml'),
           *[str(SNAPSHOT / test) for test in tests]]
with (destination / 'stdout.log').open('w', encoding='utf-8') as log:
    process = subprocess.Popen(command, cwd=destination, env=environment, stdout=log, stderr=subprocess.STDOUT)
    print(json.dumps({'pid': process.pid, 'output': str(destination)}), flush=True)
    code = process.wait()
report = {'exit_code': code, 'package_files': expected, 'package_file_count': len(expected),
          'source_wheel_installed_equal': package_hashes() == expected,
          'tests_unchanged': test_before == test_hashes(), 'test_inputs': test_before,
          'wheel_sha256': proof['wheel_sha256'], 'tests': tests,
          'scope': 'installed Core, snapshot tests only on import path, isolated synthetic homes'}
(destination / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in report.items() if key not in {'package_files', 'test_inputs'}}), flush=True)
raise SystemExit(code)
