from pathlib import Path
import json
import hashlib
import shutil
import subprocess
import sys

repo = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
temp = Path('C:/Users/jpamb/AppData/Local/Temp')
root = temp/'core053-offline-stage'
root.mkdir(exist_ok=True)
for name in ('pyproject.toml', 'tools/consumer_smoke.py', 'src/nexus_connector_core/contracts/nxl/v1/manifest.json'):
    target = root/name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo/name, target)
(root/'dist').mkdir(exist_ok=True)
for path in (temp/'okto-core-r4-053-dist').iterdir():
    if path.suffix in ('.whl','.gz'):
        shutil.copy2(path, root/'dist'/path.name)
report = {'scope':'Offline Core wheel and sdist installation on Windows/Python 3.13; not full platform matrix',
          'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'dist').iterdir()},
          'wheelhouse':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (temp/'core053-win313-wheelhouse').glob('*.whl')}}
with (root/'verification.log').open('w',encoding='utf-8') as log:
    result = subprocess.run([sys.executable, str(repo/'tools/verify_offline_artifacts.py'),
                             '--root',str(root),'--wheelhouse',str(temp/'core053-win313-wheelhouse')],
                            cwd=root, stdout=log, stderr=subprocess.STDOUT)
report['exit_code'] = result.returncode
(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(result.returncode)
