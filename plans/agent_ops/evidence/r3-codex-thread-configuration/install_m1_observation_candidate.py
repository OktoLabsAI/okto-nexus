from pathlib import Path
import hashlib
import json
import subprocess
import sys
import zipfile

root = Path('C:/Users/jpamb/AppData/Local/Temp/m1-observation-hosts-ai03jk1l')
python = root / 'venv/Scripts/python.exe'
core = Path(sys.argv[1])
expected = sys.argv[2]
assert hashlib.sha256(core.read_bytes()).hexdigest() == expected
assert not (root / 'package-proof.json').exists()
env = json.loads((root / 'environment.json').read_text(encoding='utf-8'))
with (root / 'core-install.txt').open('xb') as log:
    subprocess.run([str(python), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps',
                    '--force-reinstall', str(core)], cwd=root, env=env,
                   stdout=log, stderr=subprocess.STDOUT, check=True)
artifacts = [
    (Path('C:/Users/jpamb/AppData/Local/Temp/m1-path-fix-8rktvrtc/wheels/okto_nexus-0.3.3-py3-none-any.whl'),
     'okto_nexus', 'fdb8f37866f5332244a6916d6e6eaac433cd317d4ed2792a81bd4a3f426b49c2'),
    (Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/native/wheels/okto_nexus_connector-0.0.12-py3-none-any.whl'),
     'okto_nexus_connector', '73f1a3ba6daf1a4db6f98a9eaf7badaed0d32b151a30b4c0c6a0cf66c2eae1b5'),
    (core, 'nexus_connector_core', expected),
]
proof = {}
for wheel, module, digest in artifacts:
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == digest
    package = root / 'venv/Lib/site-packages' / module
    with zipfile.ZipFile(wheel) as archive:
        names = [n for n in archive.namelist() if n.startswith(module + '/') and not n.endswith('/')]
        installed = {str(p.relative_to(root / 'venv/Lib/site-packages')).replace('\\', '/')
                     for p in package.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        assert installed == set(names), (module, installed.symmetric_difference(names))
        for name in names:
            assert archive.read(name) == (root / 'venv/Lib/site-packages' / name).read_bytes(), name
        proof[module] = dict(wheel=str(wheel), sha256=digest, files=len(names), package=str(package))
probe = '''import importlib,json,pathlib,sys
modules=('okto_nexus','okto_nexus_connector','nexus_connector_core')
result={name:importlib.import_module(name).__file__ for name in modules}
assert all(pathlib.Path(path).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()) for path in result.values())
print(json.dumps(result))
'''
result = subprocess.run([str(python), '-I', '-c', probe], cwd=root, env=env,
                        capture_output=True, text=True, check=True)
proof['imports'] = json.loads(result.stdout)
with (root / 'pip-check.txt').open('xb') as log:
    subprocess.run([str(python), '-I', '-m', 'pip', 'check'], cwd=root, env=env,
                   stdout=log, stderr=subprocess.STDOUT, check=True)
(root / 'package-proof.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(status='QUALIFICATION_ENVIRONMENT_READY', python=str(python),
                     files=sum(v['files'] for k,v in proof.items() if k != 'imports'))))
