from pathlib import Path
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parent
python = str(root / 'venv/Scripts/python.exe')
env = json.loads((root / 'environment.json').read_bytes())
core = Path('C:/Users/jpamb/AppData/Local/Temp/dx-t34-core-qualification-uleocpu5/wheels-v2/okto_nexus_connector_core-0.0.14-py3-none-any.whl')
build = json.loads((root / 'final-v2/build.json').read_bytes())
nexus = Path(build['path'])
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(core) == 'a05e4255254f9e96241890db1ac448fd228f4bb6868a112753de8cd667989325'
assert sha(nexus) == build['sha256']
def run(label, args):
    with (root / (label + '.stdout.txt')).open('xb') as out, (root / (label + '.stderr.txt')).open('xb') as err:
        result = subprocess.run([python, '-I', '-B', '-X', 'utf8', *args], cwd=root / 'isolated', env=env,
            stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW, timeout=300)
    assert result.returncode == 0, (label, result.returncode)
run('install-final', ['-m', 'pip', 'install', '--no-index', '--no-deps', '--force-reinstall', str(core), str(nexus)])
run('pip-check-final', ['-m', 'pip', 'check'])
report = {'status': 'FINAL_CANDIDATES_INSTALLED_OFFLINE', 'python': python,
    'wheels': [{'path': str(p), 'sha256': sha(p), 'bytes': p.stat().st_size} for p in (core, nexus)],
    'provider_calls': 0, 'real_services': 0, 'M1_mutations': 0}
(root / 'installation-final.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report), flush=True)
