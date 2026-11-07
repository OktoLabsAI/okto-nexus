import json
from pathlib import Path
import subprocess

repo = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
raw = subprocess.check_output(['git', 'diff', '--name-only', '-z', 'HEAD'], cwd=repo)
raw += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=repo)
paths = sorted({name for name in raw.decode().split('\0')
    if name.endswith('.py') and name.startswith(('src/', 'tests/')) and (repo / name).is_file()})
result = subprocess.run(['ruff', 'check', *paths], cwd=repo, text=True, capture_output=True)
output = dict(paths=paths, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
target = Path(__file__).resolve().parent / 'changed-python-ruff-final.json'
assert not target.exists()
target.write_text(json.dumps(output, indent=2), encoding='utf-8')
print(json.dumps(dict(files=len(paths), exit_code=result.returncode, output=result.stdout), indent=2))
raise SystemExit(result.returncode)
