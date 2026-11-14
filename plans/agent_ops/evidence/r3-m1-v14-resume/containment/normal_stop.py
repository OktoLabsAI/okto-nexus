"""One explicit normal stop after the original stop was SERVICE_UNREACHABLE."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleanup

metadata = cleanup.read(cleanup.HERE / 'manifest.json')
cleanup.require(cleanup.sha(cleanup.HERE / 'manifest.json') == 'b85ef009a88e0e2c51b192ba11f031eab729819ee510e79402ccd6d80623348b', 'MANIFEST_CHANGED')
module = cleanup.load('resume_context', metadata['context'])
context = module.gate(SimpleNamespace(**metadata['authority']))
from okto_nexus.adapters.outbound.terminal_http import LocalOperatorHTTP
http = LocalOperatorHTTP(host='127.0.0.1', port=58631, timeout=10)
owner = http('GET', '/api/v1/service')['data']
cleanup.require(owner['pid'] == 53004 and owner['generation'] == 'cfec0795237a444636046a3541a5cd7d'
    and owner['state'] in ('ready', 'stopping'), 'EXACT_OWNER_REQUIRED')
prior = cleanup.read(context.PUBLIC / 'lifecycle-nexus-stop-result.json')
cleanup.require(prior['returncode'] == 3 and prior['reported_state'] == 'degraded', 'PRIOR_STOP_CHANGED')
command = next(step for step in context.C['steps'] if step['component'] == 'nexus' and step['action'] == 'stop')['argv']
cleanup.require('--force' not in command and command[0] == sys.executable, 'NORMAL_STOP_ONLY')
ledger = cleanup.HERE / 'runtime'
context.common.reserve(ledger / 'normal-stop-reserved.json', {'argv': command, 'owner': {
    key: owner[key] for key in ('pid', 'generation', 'instance_id')}, 'prior_stop_result_sha256': cleanup.sha(context.PUBLIC / 'lifecycle-nexus-stop-result.json'),
    'reason': 'Original normal stop could not reach service; canonical interrupt now admitted. One explicit normal stop, no force.'})
with (ledger / 'normal-stop.stdout').open('xb') as out, (ledger / 'normal-stop.stderr').open('xb') as err:
    child = subprocess.Popen(command, cwd=context.ROOT, env=context.env(), stdin=subprocess.DEVNULL,
        stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    code = child.wait()
value = cleanup.read(ledger / 'normal-stop.stdout')
result = {'cli_exit': code, 'wrapper_exit_confirmed': True,
    'observation': {key: value.get(key) for key in ('state', 'reason', 'pid', 'generation', 'shutdown')},
    'stdout_sha256': cleanup.sha(ledger / 'normal-stop.stdout'), 'stderr_sha256': cleanup.sha(ledger / 'normal-stop.stderr')}
context.common.reserve(ledger / 'normal-stop-result.json', result)
print(json.dumps(result))
raise SystemExit(code)
