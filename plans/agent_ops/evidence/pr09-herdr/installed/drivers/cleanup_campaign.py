"""Canonical cleanup of the two remaining disposable qualification servers."""
import json
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import psutil

root = Path(__file__).resolve().parent
q = root / 'qualified'
herdr = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-herdr-live.py')
launcher = json.loads((herdr['ROOT'] / 'live/restarted-launcher.json').read_text())
parent = psutil.Process(launcher['pid'])
owned = [parent, *parent.children(recursive=True)]
assert any(Path(process.exe()).resolve() == herdr['EXE'].resolve() for process in owned)
herdr['call']('fixture-final-stop', ['server', 'stop'])
gone, alive = psutil.wait_procs(owned, timeout=15)
assert not alive
status = herdr['call']('final-stopped-status', ['status', 'server', '--json'])
assert json.loads(status.stdout)['running'] is False
herdr_proof = dict(result='stopped', canonical_stop=True, running=False,
                   owned_processes_exited=sorted(process.pid for process in gone))
(herdr['ROOT'] / 'live/cleanup.json').write_text(json.dumps(herdr_proof, indent=2), encoding='utf-8')
server = json.loads((q / 'server.json').read_text())
nexus = psutil.Process(server['pid'])
result = subprocess.run(['rtk', 'proxy', sys.executable, '-X', 'utf8', str(root / 'stop_server.py')],
    cwd=q, capture_output=True, timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
assert result.returncode == 0
drain = json.loads(result.stdout)
nexus.wait(timeout=15)
probe = socket.socket()
probe.settimeout(2)
port = int(server['url'].rsplit(':', 1)[1])
connection_code = probe.connect_ex(('127.0.0.1', port))
probe.close()
assert connection_code != 0
proof = dict(result='passed', herdr=herdr_proof, nexus=dict(pid=server['pid'], exited=True,
    canonical_response=drain, tcp_connect_ex=connection_code, tcp_accepting=False),
    secondary_herdr='Already canonically stopped in independent namespace campaign; all nine owned processes exited.')
(q / 'observer-final-cleanup.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
print(json.dumps(proof))
