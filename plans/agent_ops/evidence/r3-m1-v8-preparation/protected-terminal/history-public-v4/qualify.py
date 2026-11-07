"""Two precise modeled fault boundaries and one real benign ConPTY transfer."""
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import protected_pty as helper

OUTPUT = ROOT / sys.argv[1]
OUTPUT.mkdir()
reports = []
fake_key = 'nxs_' + 'a' * 48
class FakePty:
    pid = 404
    def __init__(self, *args, **kwargs):
        pass
    def spawn(self, *args, **kwargs):
        return True
    def read(self, **kwargs):
        return helper.HEADER + '\n' + fake_key + '\n' + helper.FOOTER + '\n'
    def isalive(self):
        return True
    def get_exitstatus(self):
        return None

for target in ('producer', 'consumer'):
    progress = {'producer_started': False, 'consumer_started': False, 'consumer_start_count': 0,
                'delivery_attempted': False, 'possible_effect': False, 'possible_consumer_effect': False,
                'consumer_io_completed': False}
    def identity(job_name, pid):
        if pid == (404 if target == 'producer' else 405):
            raise OSError('injected identity failure')
        return {'pid': pid, 'birth_filetime': 1, 'exact_job_member': True}
    fake_consumer = SimpleNamespace(pid=405)
    spec = {'job_name': 'synthetic-fake-only', 'producer_argv': ['C:/Python313/python.exe'],
            'consumer_argv': ['C:/Python313/python.exe'], 'env': {}, 'consumer_env': {},
            'cwd': str(OUTPUT), 'timeout_seconds': 20, 'synthetic_probe': False}
    fake_winpty = SimpleNamespace(PTY=FakePty, Backend=SimpleNamespace(ConPTY=1), WinptyError=RuntimeError)
    with patch.dict(sys.modules, {'winpty': fake_winpty}), patch.object(helper, 'job_identity', identity), \
         patch.object(helper.subprocess, 'Popen', return_value=fake_consumer) as popen:
        try:
            helper._worker(spec, progress)
        except OSError:
            pass
        else:
            raise AssertionError('identity fault was not observed')
        assert progress['producer_started'] and progress['possible_effect']
        assert not progress['delivery_attempted']
        if target == 'producer':
            assert popen.call_count == 0 and not progress['consumer_started']
        else:
            assert popen.call_count == 1
            assert progress['consumer_started'] and progress['possible_consumer_effect']
            assert progress['consumer_start_count'] == 1
    report = {'case': target + '-identity-failure', 'status': 'PASS', 'kind': 'injected_boundary_model',
              'actual_processes_started': 0, 'progress': progress}
    reports.append(report)
    (OUTPUT / ('result-' + target + '-identity-failure.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)

case = OUTPUT / 'cooperative'
case.mkdir()
env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
env.update(PATH='C:/Python313;C:/Windows/System32', HOME=str(case), USERPROFILE=str(case),
           APPDATA=str(case), LOCALAPPDATA=str(case), TEMP=str(case), TMP=str(case), PYTHONUTF8='1')
result = helper.transfer_once(
    producer_argv=['C:/Python313/python.exe', '-I', str(ROOT / 'cooperative_producer.py'), 'cooperative'],
    consumer_argv=['C:/Python313/python.exe', '-I', str(ROOT / 'cooperative_consumer.py'), 'cooperative'],
    env=env, consumer_env={**env, 'OKTO_NEXUS_CONNECTER_DAEMON_FG': '1'},
    cwd=case, timeout_seconds=20, synthetic_probe=True)
result.update(case='cooperative', kind='real_benign_conpty',
              material_received_marker=(case / 'consumer-ack.json').exists(),
              producer_finished_after_consumer_signal=(case / 'producer-saw-ack.json').exists())
(OUTPUT / 'result-cooperative.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result), flush=True)
assert result['status'] == 'TRANSFERRED_ONCE' and result['active_job_processes_after'] == 0
assert result['producer_exit'] == result['consumer_exit'] == 0
assert result['producer_alive_at_consumer_start'] and result['producer_finished_after_consumer_signal']
assert result['consumer_start_count'] == 1 and result['delivery_attempted']
assert result['consumer_material_matches'] and not result['forced_owned_cleanup']
reports.append(result)
summary = {'status': 'SYNTHETIC_ONLY_PASS', 'case_count': 3, 'cases': reports,
           'product_cli_calls': 0, 'real_credentials': 0, 'providers': 0,
           'limit': 'Two fault-boundary models plus one real benign ConPTY transfer. Prior seven cases remain historical V3 evidence, not rerun here.',
           'source_hashes': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                             for name in ('protected_pty.py', 'owned_job.py', 'cooperative_producer.py', 'cooperative_consumer.py', 'qualify.py')}}
(OUTPUT / 'qualification.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
