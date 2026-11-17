"""Normal stop-file shutdown of own finite observer; no WSL termination."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

ROOT = Path('/tmp/nexus-qc28-xmlie7rv')
HERE = Path('/mnt/d/Projetos/Techridy/okto_labs_okto_nexus/NEXUS_QUICK_CONNECT_R1/execution/qc28-posix-paths')
assert (HERE / 'qualification.json').exists() and (HERE / 'evidence/result.json').exists()
pid = 398
proc = Path('/proc') / str(pid)
command = (proc / 'cmdline').read_bytes()
assert b'nexus-qc28-' in command and b'stop-keeper' in command
assert proc.stat().st_uid == os.getuid()
parts = (proc / 'stat').read_text().split(') ', 1)[1].split()
start = parts[19]
result = json.loads((ROOT / 'result.json').read_text())
groups = {r['pid'] for r in result['cases']} if 'pid' in result['cases'][0] else set()
# The runner records completed groups and their absence immediately after each
# cut. No other user/distro process is inspected for control or signaled here.
assert all(not r['remaining_process_group'] for r in result['cases'])
(ROOT / 'stop-keeper').touch()
until = time.monotonic() + 10
alive, state = True, None
while time.monotonic() < until:
    try:
        now = (proc / 'stat').read_text().split(') ', 1)[1].split()
        state = now[0]
        alive = now[19] == start and state != 'Z'
    except FileNotFoundError:
        state, alive = 'absent', False
    if not alive:
        break
    time.sleep(.1)
value = dict(observed_at=datetime.now(timezone.utc).isoformat(), keeper_pid=pid, birth_ticks=start,
    command_sha256=hashlib.sha256(command).hexdigest(), stop='own stop-keeper file',
    alive=alive, final_state=state, signal_used=False, WSL_shutdown_or_terminate_used=False,
    pytest_groups_remaining=[], copied_evidence_verified_before_stop=True,
    exact_keeper_exit_code='Not reaped by this process; normal stop and /proc state observed separately.')
(HERE / 'cleanup.json').write_text(json.dumps(value, indent=2) + '\n')
print(json.dumps(value))
assert not alive
