from pathlib import Path
import json
import subprocess

root = Path(__file__).resolve().parent
env = json.loads((root / 'environment.json').read_bytes())
with (root / 'installed-nexus-v2.stdout.txt').open('xb') as out, (root / 'installed-nexus-v2.stderr.txt').open('xb') as err:
    result = subprocess.run([str(root / 'venv/Scripts/python.exe'), '-I', '-B', '-X', 'utf8', str(root / 'installed_nexus_runner_v2.py')],
        cwd=root / 'isolated', env=env, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW, timeout=300)
print((root / 'installed-nexus-v2.stdout.txt').read_text(encoding='utf-8'))
print((root / 'installed-nexus-v2.stderr.txt').read_text(encoding='utf-8'))
raise SystemExit(result.returncode)
