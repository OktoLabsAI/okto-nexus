"""Finite synthetic preparation only; never launches a provider or service."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).parent
PYTHON = Path('C:/Users/jpamb/AppData/Local/Temp/m1-drain-hosts-n7pm3omg/venv/Scripts/python.exe')
output = HERE / sys.argv[1]
output.mkdir()
home = output / 'home'
home.mkdir()
environment = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
environment.update(PATH=str(PYTHON.parent) + ';' + str(Path(environment['SYSTEMROOT']) / 'System32'),
                   HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home),
                   TEMP=str(home), TMP=str(home), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1')
inputs = list(HERE.glob('*.py'))
def hashes(): return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
before = hashes()
(output / 'inputs-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
child = output / 'run.py'
child.write_text('''import sys, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import nexus_connector_core, okto_nexus, pytest
paths = {"core": nexus_connector_core.__file__, "nexus": okto_nexus.__file__}
assert all(Path(value).resolve().is_relative_to(Path(sys.prefix).resolve()) for value in paths.values())
Path(sys.argv[2]).write_text(json.dumps(paths, indent=2))
raise SystemExit(pytest.main(sys.argv[3:]))
''', encoding='utf-8')
with (output / 'stdout.log').open('w', encoding='utf-8') as log:
    process = subprocess.Popen([str(PYTHON), '-I', str(child), str(HERE), str(output / 'imports.json'),
        '-q', '--tb=short', '-o', 'cache_dir=' + str(output / 'cache'), '--basetemp=' + str(output / 'pytest'),
        '--junitxml=' + str(output / 'tests.xml'), str(HERE / 'test_v8.py')],
        cwd=output, env=environment, stdout=log, stderr=subprocess.STDOUT)
    print(json.dumps({'pid': process.pid, 'output': str(output)}), flush=True)
    code = process.wait()
report = {'exit_code': code, 'inputs_unchanged': before == hashes(),
          'scope': 'Synthetic transport + installed pure Core translation; no provider/network/vault/service',
          'campaign_authorized': False, 'inputs_after': hashes()}
(output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in report.items() if key != 'inputs_after'}), flush=True)
raise SystemExit(code)
