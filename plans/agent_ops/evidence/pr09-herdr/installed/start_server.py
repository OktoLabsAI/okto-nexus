"""Start the installed foreground CLI in a hidden process; retain it for QA."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent / 'qualified'
HOME = ROOT / 'server-home'
HOME.mkdir()
python = ROOT / 'venv/Scripts/python.exe'
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
env = {key: value for key, value in os.environ.items()
       if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PATH', 'TEMP', 'TMP'}}
env.update(HOME=str(HOME), USERPROFILE=str(HOME), APPDATA=str(HOME / 'appdata'),
           LOCALAPPDATA=str(HOME / 'localappdata'), PYTHONDONTWRITEBYTECODE='1',
           OKTO_NEXUS_NO_BANNER='1', OKTO_NEXUS_LOG_LEVEL='warning')
log = ROOT / 'server.log'
with log.open('x', encoding='utf-8') as output:
    process = subprocess.Popen([str(python), '-B', '-P', '-X', 'utf8',
        str(Path(__file__).with_name('server_entry.py')), sys.argv[1], str(port), sys.argv[2]],
        cwd=HOME, env=env, stdout=output, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
metadata = {'url': f'http://127.0.0.1:{port}', 'pid': process.pid, 'home': str(HOME),
            'log': str(log), 'python': str(python),
            'shutdown': 'GET /api/v1/service then POST /api/v1/service/stop with current instance_id and generation',
            'launcher': str(Path(__file__).with_name('server_entry.py'))}
(ROOT / 'server.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
from urllib.request import ProxyHandler, build_opener
urlopen = build_opener(ProxyHandler({})).open
for _ in range(100):
    if process.poll() is not None:
        raise RuntimeError(f'Server exited {process.returncode}; inspect {log}')
    try:
        with urlopen(metadata['url'] + '/api/v1/service', timeout=1) as response:
            state = json.load(response)
        if state.get('ok') and state['data'].get('state') in ('ready', 'READY', 'RUNNING'):
            break
        if state.get('ok') and state['data'].get('ready'):
            break
        with urlopen(metadata['url'] + '/healthz', timeout=1):
            break
    except (OSError, ValueError):
        time.sleep(.3)
else:
    raise RuntimeError('Server readiness timed out; retained metadata and process for diagnosis')
with urlopen(metadata['url'] + '/api/v1/service', timeout=2) as response:
    service = json.load(response)['data']
(ROOT / 'server-owner.json').write_text(json.dumps({'server_pid': service['pid'],
    'generation': service['generation'], 'instance_id': service['instance_id']}, indent=2), encoding='utf-8')
print(json.dumps(metadata, indent=2))
