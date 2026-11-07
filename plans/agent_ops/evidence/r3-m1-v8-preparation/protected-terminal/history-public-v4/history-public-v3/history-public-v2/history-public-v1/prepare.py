import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).parent
name = 'pywinpty-3.0.3-cp313-cp313-win_amd64.whl'
expected = '9c91dbb026050c77bdcef964e63a4f10f01a639113c4d3658332614544c467ab'
metadata = json.load(urllib.request.urlopen('https://pypi.org/pypi/pywinpty/3.0.3/json', timeout=30))
entry, = [item for item in metadata['urls'] if item['filename'] == name]
assert entry['digests']['sha256'] == expected
wheel = ROOT / name
data = urllib.request.urlopen(entry['url'], timeout=30).read()
assert hashlib.sha256(data).hexdigest() == expected
wheel.write_bytes(data)
env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
home = ROOT / 'prepare-home'
home.mkdir()
env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home),
           TEMP=str(home), TMP=str(home), PATH='C:/Python313;C:/Windows/System32', PIP_CONFIG_FILE='NUL')
commands = [[sys._base_executable, '-I', '-m', 'venv', str(ROOT / 'venv')],
    [str(ROOT / 'venv/Scripts/python.exe'), '-I', '-m', 'pip', '--isolated', 'install', '--no-index', '--no-deps', str(wheel)]]
with (ROOT / 'prepare.log').open('w', encoding='utf-8') as log:
    for command in commands:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
(ROOT / 'dependency.json').write_text(json.dumps({'name': 'pywinpty', 'version': '3.0.3',
    'wheel': name, 'sha256': expected, 'url': entry['url'],
    'source': 'https://github.com/andfoy/pywinpty/tree/v3.0.3'}, indent=2), encoding='utf-8')
print(json.dumps({'prepared': True, 'root': str(ROOT), 'wheel_sha256': expected}))
