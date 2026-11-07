from pathlib import Path
import hashlib, json, os, shutil, subprocess, tempfile, venv

root = Path(tempfile.mkdtemp(prefix='m1-drain-hosts-'))
print(json.dumps({'root': str(root), 'status': 'PREPARING'}), flush=True)
target = root / 'venv'
venv.EnvBuilder(with_pip=False).create(target)
source = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv/Lib/site-packages')
shutil.copytree(source, target / 'Lib/site-packages', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
wheel = Path('C:/Users/jpamb/AppData/Local/Temp/m1-path-fix-8rktvrtc/wheels/okto_nexus-0.3.3-py3-none-any.whl')
assert hashlib.sha256(wheel.read_bytes()).hexdigest() == 'fdb8f37866f5332244a6916d6e6eaac433cd317d4ed2792a81bd4a3f426b49c2'
env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP'}}
for name in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA'):
    folder = root / 'isolated' / name.lower()
    folder.mkdir(parents=True)
    env[name] = str(folder)
env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OKTO_NEXUS_NO_BANNER='1')
(root / 'environment.json').write_text(json.dumps(env, indent=2) + '\n')
with (root / 'nexus-install.txt').open('wb') as log:
    subprocess.run([str(target / 'Scripts/python.exe'), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps', '--force-reinstall', str(wheel)], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
(root / 'preparation.json').write_text(json.dumps(dict(status='AWAITING_CORE_CANDIDATE', python=str(target / 'Scripts/python.exe'), nexus_wheel=str(wheel), dependency_source=str(source), personal_credentials_forwarded=False, runtime_effects=False), indent=2) + '\n')
print(json.dumps(dict(root=str(root), status='AWAITING_CORE_CANDIDATE')), flush=True)
