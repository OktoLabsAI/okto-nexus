from pathlib import Path
import json, os, subprocess, sys

root = Path('C:/Users/jpamb/AppData/Local/Temp/m1-path-fix-8rktvrtc')
lane = sys.argv[1]
assert lane in ('historical-reproducer', 'fixed-installed')
out = root / lane
out.mkdir(exist_ok=False)
env = {k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP'}}
for name in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA'):
    folder = out / name.lower()
    folder.mkdir()
    env[name] = str(folder)
env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OKTO_NEXUS_NO_BANNER='1')
if lane == 'historical-reproducer':
    python = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv/Scripts/python.exe')
    wheel = Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/native/wheels/okto_nexus-0.3.3-py3-none-any.whl')
    selected = 'tests/execution_r4/test_terminal_connect.py::test_provider_home_separators_survive_finish_and_read_only_resume'
else:
    python = root / 'venv/Scripts/python.exe'
    wheel = root / 'wheels/okto_nexus-0.3.3-py3-none-any.whl'
    selected = 'tests/execution_r4/test_terminal_connect.py'
command = [str(python), '-I', '-X', 'utf8', str(root / 'source/tools/ci_installed.py'), 'test', '--wheel', str(wheel), '--output', str(out / 'canonical'), '--tests', selected]
(out / 'command.json').write_text(json.dumps(dict(command=command, personal_profile_forwarded=False, native_service_registration=False, real_provider=False), indent=2) + '\n')
with (out / 'test-output.txt').open('wb') as log:
    result = subprocess.run(command, cwd=out, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
print(json.dumps(dict(lane=lane, returncode=result.returncode, output=str(out))))
sys.exit(result.returncode)
