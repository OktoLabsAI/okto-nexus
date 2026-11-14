"""Normal cleanup of this completed, failed disposable campaign only."""
import copy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import runtime_support as s

assert s.sha(ROOT / 'plan.json') == 'a0029067431029c8caa7b28632b2c77f8bb564efb41cfe63332e126912478d50'
plan = s.read(ROOT / 'plan.json')
assert Path(sys.executable).resolve() == Path(plan['python']).resolve()
assert s.read(s.PUBLIC / 'progression-failed.json')['code'] == 'READINESS_TIMEOUT_NO_RETRY'
assert s.read(s.PUBLIC / 'nexus-crash-0.json')['exit_confirmed'] is True
os.environ.clear()
os.environ.update(plan['environments']['A'])
from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation
from okto_nexus_connector.platform.user_service import UserService
services = {
    'nexus': ServerInstallation(Path(plan['homes']['nexus']), Path(plan['homes']['nexus']) / 'nexus.db'),
    'connector': UserService(Path(plan['homes']['connector'])),
}
assert all(service.name == plan['tasks'][name] for name, service in services.items())
assert services['connector'].tasks.read(services['connector'].name) is None
s.save(s.PRIVATE / 'root-normal-cleanup-reserved.json', {'plan_sha256': s.sha(ROOT / 'plan.json'), 'normal_only': True})
for name in ('nexus',):
    service = services[name]
    plan['commands'][name]['cleanup-normal-stop'] = copy.deepcopy(plan['commands'][name]['stop-after-exhaustion'])
    code, result = s.cli(plan, name, 'cleanup-normal-stop')
    assert code == 0 and result.get('shutdown_outcome') == 'drained', 'NORMAL_STOP_UNCONFIRMED'
    current = s.inspect(plan, name)
    assert current.get('state') == 'stopped' and current.get('pid') is None, 'STOP_NOT_CONFIRMED'
    task = service.tasks.read(service.name)
    assert task and not task.active, 'NATIVE_TASK_NOT_INACTIVE'
    before = s.fingerprint(Path(plan['homes'][name]), plan['uninstall_removes'][name])
    plan['commands'][name]['cleanup-uninstall'] = copy.deepcopy(plan['commands'][name]['uninstall'])
    code, _ = s.cli(plan, name, 'cleanup-uninstall')
    assert code == 0 and service.tasks.read(service.name) is None, 'UNINSTALL_NOT_CONFIRMED'
    after = s.fingerprint(Path(plan['homes'][name]), plan['uninstall_removes'][name])
    s.validate_preservation(before, after)
    s.save(s.PUBLIC / 'root-cleanup-data-retained.json', {'before': before, 'after': after, 'identical': True})
s.port_available(plan)
assert all(service.tasks.read(service.name) is None for service in services.values())
s.save(s.PUBLIC / 'root-normal-cleanup.json', {'normal_stop': 'drained', 'tasks_absent': True, 'port_available': True, 'data_preserved': True, 'force_used': False, 'model_turns': 0, 'original_failure_preserved': True})
print(json.dumps({'status': 'NORMAL_CLEANUP_CONFIRMED'}))
