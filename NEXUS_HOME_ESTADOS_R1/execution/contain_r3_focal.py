"""One-time containment of the stuck, identity-verified own source test reader."""
from datetime import UTC, datetime
import json
from pathlib import Path
import time

import psutil

ROOT = Path(__file__).resolve().parents[2]
parent = psutil.Process(60580)
assert parent.create_time() == 1794930189.1458955
assert Path(parent.exe()) == Path('C:/Python313/python.exe')
args = parent.cmdline()
assert any(value.endswith('run_home_states_tests.py') for value in args)
assert args[args.index('--label') + 1] == 'r3-focal'
target = psutil.Process(53008)
assert target.create_time() == 1794930189.512396
assert Path(target.exe()) == Path('C:/Python313/python.exe')
assert target.pid in {child.pid for child in parent.children(recursive=True)}
assert 'nexus-hst-source-8rv1wvh4' in ' '.join(target.cmdline())
known = [dict(pid=p.pid, birth=p.create_time(), exe=p.exe())
         for p in [parent, *parent.children(recursive=True)]]
report = {'at': datetime.now(UTC).isoformat(),
          'reason': 'Own gap fixture did not exit for over 17 minutes; no live HTTP service endpoint for in-process TestClient teardown.',
          'result': 'INCOMPLETE_NOT_PASS', 'known_before': known,
          'action': {'kind': 'kill_verified_own_pytest', 'pid': target.pid,
                     'birth': target.create_time(), 'exe': target.exe()},
          'data_preserved': True,
          'limitations': ['Late ancestry observation does not establish completeness of all short-lived descendants.']}
target.kill()
psutil.wait_procs([target], timeout=15)
until = time.monotonic() + 15
while time.monotonic() < until and any(psutil.pid_exists(row['pid']) for row in known):
    time.sleep(.1)
report['remaining_same_identity'] = []
for row in known:
    try:
        p = psutil.Process(row['pid'])
        if p.create_time() == row['birth'] and p.exe() == row['exe']:
            report['remaining_same_identity'].append(row)
    except psutil.NoSuchProcess:
        pass
path = ROOT / 'NEXUS_HOME_ESTADOS_R1/execution/source-tests/r3-focal-containment.json'
path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'report': str(path), 'remaining': report['remaining_same_identity']}))
