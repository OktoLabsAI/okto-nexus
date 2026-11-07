from pathlib import Path
import hashlib, json, subprocess, zipfile

root = Path('C:/Users/jpamb/AppData/Local/Temp/m1-drain-hosts-n7pm3omg')
python = root / 'venv/Scripts/python.exe'
core = Path('C:/Users/jpamb/AppData/Local/Temp/core-eviction-drain-ru1nczz0/candidate/wheels/okto_nexus_connector_core-0.0.14-py3-none-any.whl')
assert hashlib.sha256(core.read_bytes()).hexdigest() == '4e677a205f5a486ef7134b8411983420c1c763c3dda274128a9c623ad1b1775d'
env = json.loads((root / 'environment.json').read_text())
with (root / 'core-install.txt').open('wb') as log:
    subprocess.run([str(python), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps', '--force-reinstall', str(core)], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
artifacts = [
    (Path('C:/Users/jpamb/AppData/Local/Temp/m1-path-fix-8rktvrtc/wheels/okto_nexus-0.3.3-py3-none-any.whl'), 'okto_nexus'),
    (Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/native/wheels/okto_nexus_connector-0.0.12-py3-none-any.whl'), 'okto_nexus_connector'),
    (core, 'nexus_connector_core'),
]
proof = {}
for wheel, module in artifacts:
    package = root / 'venv/Lib/site-packages' / module
    with zipfile.ZipFile(wheel) as archive:
        names = [n for n in archive.namelist() if n.startswith(module + '/') and not n.endswith('/')]
        for name in names:
            assert archive.read(name) == (root / 'venv/Lib/site-packages' / name).read_bytes(), name
        proof[module] = dict(wheel=str(wheel), sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(), files=len(names), package=str(package))
probe = '''import importlib,json,pathlib,sys
modules=('okto_nexus','okto_nexus_connector','nexus_connector_core')
result={name:importlib.import_module(name).__file__ for name in modules}
assert all(pathlib.Path(path).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()) for path in result.values())
print(json.dumps(result))
'''
result = subprocess.run([str(python), '-I', '-c', probe], cwd=root, env=env, capture_output=True, text=True, check=True)
proof['imports'] = json.loads(result.stdout)
with (root / 'pip-check.txt').open('wb') as log:
    check = subprocess.run([str(python), '-I', '-m', 'pip', 'check'], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
assert check.returncode == 0
(root / 'package-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps(dict(status='QUALIFICATION_ENVIRONMENT_READY', python=str(python), packages={name: value['sha256'] for name, value in proof.items() if name != 'imports'}, files=sum(value['files'] for name, value in proof.items() if name != 'imports'))))
