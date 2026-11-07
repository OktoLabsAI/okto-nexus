from pathlib import Path
import json
import os
import shutil
import tempfile
import venv

root = Path(tempfile.mkdtemp(prefix='m1-observation-hosts-'))
print(json.dumps({'root': str(root), 'status': 'PREPARING'}), flush=True)
target = root / 'venv'
venv.EnvBuilder(with_pip=False).create(target)
source = Path('C:/Users/jpamb/AppData/Local/Temp/m1-drain-hosts-n7pm3omg/venv/Lib/site-packages')
shutil.copytree(source, target / 'Lib/site-packages', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
env = {k: v for k, v in os.environ.items() if k.upper() in
       {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP'}}
for name in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA'):
    folder = root / 'isolated' / name.lower()
    folder.mkdir(parents=True)
    env[name] = str(folder)
env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OKTO_NEXUS_NO_BANNER='1')
(root / 'environment.json').write_text(json.dumps(env, indent=2)+'\n', encoding='utf-8')
(root / 'preparation.json').write_text(json.dumps({
    'status': 'AWAITING_CORE_OBSERVATION_CANDIDATE',
    'python': str(target / 'Scripts/python.exe'),
    'dependency_source': str(source),
    'historical_environments_modified': False,
    'personal_credentials_forwarded': False,
    'runtime_effects': False,
}, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'root': str(root), 'status': 'AWAITING_CORE_OBSERVATION_CANDIDATE'}), flush=True)
