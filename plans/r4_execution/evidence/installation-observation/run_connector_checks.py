import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

repo = Path('D:/Projetos/Techridy/okto-nexus-connector')
out = Path('C:/Users/jpamb/AppData/Local/Temp/connector-observation-installed')
out.mkdir(exist_ok=True)
wheel = Path('C:/Users/jpamb/AppData/Local/Temp/connector-observation-dist/okto_nexus_connector-0.5.0.dev0-py3-none-any.whl')
import okto_nexus_connector
package = Path(okto_nexus_connector.__file__).parent
assert 'site-packages' in str(package)
with zipfile.ZipFile(wheel) as archive:
    names = [n for n in archive.namelist() if n.startswith('okto_nexus_connector/') and not n.endswith('/')]
    assert all((package / n.split('/', 1)[1]).read_bytes() == archive.read(n) for n in names)
def hashes():
    files = [repo/'README.md', repo/'pyproject.toml']
    for directory in ('src', 'tests', 'docs'):
        files.extend(p for p in (repo/directory).rglob('*') if p.is_file() and p.suffix in ('.py', '.md', '.json'))
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}
before = hashes()
report = dict(status='RUNNING', started_at=datetime.now(timezone.utc).isoformat(),
              wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
              module=str(package), verified_files=len(names), input_hashes=before)
(out/'campaign.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
env = dict(os.environ, OKTO_NEXUS_CONNECTOR_VAULT='file')
command = ['rtk', 'proxy', sys.executable, '-I', '-m', 'pytest', '-q', '-o', 'pythonpath=',
           'tests', '--junitxml='+str(out/'tests.xml')]
with (out/'pytest.log').open('w', encoding='utf-8') as log:
    result = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
after = hashes()
changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
report.update(status='INPUTS_CHANGED' if changed else 'PASS' if result.returncode == 0 else 'FAIL',
              exit_code=result.returncode, changed_inputs=changed, command=command,
              ended_at=datetime.now(timezone.utc).isoformat())
(out/'campaign.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print((out/'pytest.log').read_text(encoding='utf-8')[-5000:])
print(json.dumps({k:v for k,v in report.items() if k!='input_hashes'}))
raise SystemExit(result.returncode or bool(changed))
