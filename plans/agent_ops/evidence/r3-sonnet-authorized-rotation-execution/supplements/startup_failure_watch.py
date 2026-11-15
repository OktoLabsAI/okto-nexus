from pathlib import Path
import json, sys, time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recovery_context import RecoveryContext, require, sha
from recovery_observation import cycle, Process, ROLES
root = Path(__file__).resolve().parent
x = RecoveryContext(root/'lifecycle-plan.json', '8980570ab636b7836ffa34a5976652c0cc19825af015c50d50a9c5b08bcf6a27')
c = cycle(x)
require(c['cycle_id'] == '83385b0dffad1b22ee9fdd49842429ca', 'CYCLE_CHANGED')
require(c['child']['pid'] == 14264, 'OWNER_CHANGED')
handles = {}
try:
    for role in ROLES:
        h = Process(c[role]['pid'])
        handles[role] = h
        require(h.birth == c[role]['birth'] and h.image in x.installed['python_images'] and sha(h.image) == x.installed['python_images'][h.image], 'IDENTITY_CHANGED')
    require(cycle(x) == c, 'CYCLE_CHANGED')
    x.save('startup-failure-watch-started.json', {'cohort': c, 'observer_pid': __import__('os').getpid(), 'ready_claimed': False, 'terminate_right': False})
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        if all(h.exited() for h in handles.values()):
            value = {'cohort': c, 'exits': {r: {'pid': h.pid, 'birth': h.birth, 'physical_exit': True, 'exit_code': h.exit_code()} for r,h in handles.items()}, 'ready_claimed': False}
            x.save('startup-failure-exit-proof.json', value)
            print(json.dumps(value))
            break
        time.sleep(0.2)
    else:
        x.save('startup-failure-watch-timeout.json', {'physical_exit_confirmed': False})
        raise RuntimeError('OBSERVATION_TIMEOUT')
finally:
    for h in handles.values(): h.close()
