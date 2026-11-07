"""Start only this installed disposable Server in a hidden process."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parent / 'qualified'
SERVER_HOME = ROOT / 'server-home'
SERVER_HOME.mkdir()
python = ROOT / 'venv/Scripts/python.exe'
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
env = {key: value for key, value in os.environ.items()
       if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PATH', 'TEMP', 'TMP'}}
env.update(USERPROFILE=str(SERVER_HOME), APPDATA=str(SERVER_HOME / 'appdata'),
    LOCALAPPDATA=str(SERVER_HOME / 'localappdata'), PYTHONDONTWRITEBYTECODE='1',
    OKTO_NEXUS_NO_BANNER='1', OKTO_NEXUS_LOG_LEVEL='warning')
log = ROOT / 'server.log'
with log.open('x', encoding='utf-8') as output:
    process = subprocess.Popen([str(python), '-B', '-P', '-X', 'utf8',
        str(Path(__file__).with_name('server_entry.py')), sys.argv[1], str(port), sys.argv[2]],
        cwd=SERVER_HOME, env=env, stdout=output, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
metadata = dict(url=f'http://127.0.0.1:{port}', pid=process.pid, home=str(SERVER_HOME),
    log=str(log), python=str(python), shutdown='Canonical owner-fenced /api/v1/service/stop',
    launcher=str(Path(__file__).with_name('server_entry.py')))
(ROOT / 'server.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
urlopen = build_opener(ProxyHandler({})).open
for _ in range(100):
    if process.poll() is not None:
        raise RuntimeError(f'Server exited {process.returncode}; retained log {log}')
    try:
        with urlopen(metadata['url'] + '/api/v1/service', timeout=1) as response:
            service = json.load(response)['data']
        if service.get('ready') or service.get('state') in ('ready', 'READY', 'RUNNING'):
            break
        with urlopen(metadata['url'] + '/healthz', timeout=1):
            break
    except (OSError, ValueError, KeyError):
        time.sleep(.3)
else:
    raise RuntimeError('Server readiness timed out; retained process and metadata for diagnosis')
with urlopen(metadata['url'] + '/api/v1/service', timeout=2) as response:
    service = json.load(response)['data']
(ROOT / 'server-owner.json').write_text(json.dumps(dict(server_pid=service['pid'],
    generation=service['generation'], instance_id=service['instance_id']), indent=2), encoding='utf-8')
print(json.dumps(metadata, indent=2))
