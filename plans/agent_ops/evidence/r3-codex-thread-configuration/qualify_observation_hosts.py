from pathlib import Path
import json
import subprocess
import sys

root = Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l')
lane = sys.argv[1]
assert lane in ('nexus', 'connector')
out = root / (lane + '-qualification')
out.mkdir(exist_ok=False)
env = json.loads((root / 'environment.json').read_text(encoding='utf-8'))
for name in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA'):
    folder = out / name.lower()
    folder.mkdir()
    env[name] = str(folder)
python = root / 'venv/Scripts/python.exe'
if lane == 'nexus':
    command = [str(python), '-I', '-X', 'utf8', str(root / 'nexus-source/tools/ci_installed.py'), 'test',
               '--wheel', 'C:/Users/jpamb/AppData/Local/Temp/m1-path-fix-8rktvrtc/wheels/okto_nexus-0.3.3-py3-none-any.whl',
               '--output', str(out / 'canonical'), '--tests',
               'tests/execution_r4/test_canonical_event_views.py']
else:
    command = [str(python), '-I', '-X', 'utf8', str(root / 'connector_installed_regression.py')]
(out / 'command.json').write_text(json.dumps(dict(command=command, real_provider=False,
                                                 real_os_services=False, personal_profile_forwarded=False), indent=2)+'\n')
with (out / 'test-output.txt').open('xb') as log:
    result = subprocess.run(command, cwd=out, env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT)
print(json.dumps(dict(lane=lane, exit_code=result.returncode, output=str(out))))
sys.exit(result.returncode)
