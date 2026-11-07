import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
HERE = Path(__file__).parent
PYTHON = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv/Scripts/python.exe')
name = sys.argv[1]
tests = sys.argv[2:]
destination = HERE / name
destination.mkdir(exist_ok=False)
home = destination / 'home'
home.mkdir()
environment = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
environment.update(PATH=str(PYTHON.parent) + ';' + str(Path(environment['SYSTEMROOT']) / 'System32'),
                   HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home),
                   TEMP=str(home), TMP=str(home), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1')
child = destination / 'run.py'
child.write_text('''import sys, json
from pathlib import Path
sys.path[:0] = [str(Path(sys.argv[1]) / 'src'), str(Path(sys.argv[1]) / 'tests')]
import nexus_connector_core, pytest
Path(sys.argv[2]).write_text(json.dumps({'core_import': nexus_connector_core.__file__, 'python': sys.executable}, indent=2))
raise SystemExit(pytest.main(sys.argv[3:]))
''', encoding='utf-8')
inputs = [p for parent in (ROOT / 'src', ROOT / 'tests') for p in parent.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts]
def hashes():
    return {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in inputs}
before = hashes()
(destination / 'input-hashes-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
command = [str(PYTHON), '-I', str(child), str(ROOT), str(destination / 'imports.json'),
           '-p', 'pytest_asyncio.plugin', '-q', '--tb=short', '-o', 'cache_dir=' + str(destination / 'cache'),
           '--basetemp=' + str(destination / 'pytest'), '--junitxml=' + str(destination / 'tests.xml'),
           *[str(ROOT / test) for test in tests]]
with (destination / 'stdout.log').open('w', encoding='utf-8') as log:
    process = subprocess.Popen(command, cwd=destination, env=environment, stdout=log, stderr=subprocess.STDOUT)
    print(json.dumps({'pid': process.pid, 'output': str(destination)}), flush=True)
    code = process.wait()
after = hashes()
(destination / 'result.json').write_text(json.dumps({'exit_code': code, 'inputs_unchanged': before == after,
    'tests': tests, 'scope': 'Core source + synthetic peers, isolated home, installed test dependencies'}, indent=2), encoding='utf-8')
print(json.dumps({'exit_code': code, 'inputs_unchanged': before == after}), flush=True)
raise SystemExit(code)
