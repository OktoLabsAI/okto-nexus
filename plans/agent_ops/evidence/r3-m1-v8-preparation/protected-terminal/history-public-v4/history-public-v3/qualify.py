import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from protected_pty import transfer_once

OUTPUT = ROOT / sys.argv[1]
OUTPUT.mkdir()
reports = []
modes = ('cooperative', 'ambiguous-before', 'ambiguous-after', 'producer-deadline',
         'consumer-deadline', 'consumer-nonzero', 'installed-functions')
for mode in modes:
    case = OUTPUT / mode
    case.mkdir()
    env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
    env.update(PATH='C:/Python313;C:/Windows/System32', HOME=str(case), USERPROFILE=str(case),
               APPDATA=str(case), LOCALAPPDATA=str(case), TEMP=str(case), TMP=str(case), PYTHONUTF8='1')
    result = transfer_once(producer_argv=['C:/Python313/python.exe', '-I', str(ROOT / 'cooperative_producer.py'), mode],
        consumer_argv=['C:/Python313/python.exe', '-I', str(ROOT / 'cooperative_consumer.py'), mode],
        env=env, consumer_env={**env, 'OKTO_NEXUS_CONNECTER_DAEMON_FG': '1'},
        cwd=case, timeout_seconds=5 if 'deadline' in mode else 20, synthetic_probe=True)
    result.update(case=mode, consumer_marker=(case / 'consumer-started.json').exists(),
                  material_received_marker=(case / 'consumer-ack.json').exists(),
                  producer_finished_after_consumer_signal=(case / 'producer-saw-ack.json').exists())
    reports.append(result)
    (OUTPUT / ('result-' + mode + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    assert result['active_job_processes_after'] == 0
    if mode in ('cooperative', 'installed-functions'):
        assert result['status'] == 'TRANSFERRED_ONCE' and result['consumer_material_matches']
        assert result['producer_alive_at_consumer_start']
        assert result['producer_finished_after_consumer_signal']
        assert result['consumer_start_count'] == 1 and result['delivery_attempted']
        assert result['producer_exit'] == result['consumer_exit'] == 0
        assert not result['forced_owned_cleanup']
    elif mode in ('ambiguous-before', 'producer-deadline'):
        assert result['status'] == 'UNCONFIRMED'
        assert result['consumer_start_count'] == 0 and not result['delivery_attempted']
        assert not result['consumer_marker'] and not result['material_received_marker']
    else:
        assert result['status'] == 'UNCONFIRMED' and result['possible_effect']
        assert result['possible_consumer_effect'] and result['consumer_start_count'] == 1
        assert result['delivery_attempted'] and result['material_received_marker']
summary = {'status': 'SYNTHETIC_ONLY_PASS', 'cases': reports, 'product_cli_calls': 0,
           'providers': 0, 'real_credentials': 0,
           'installed_functions': ['okto_nexus.adapters.inbound.cli.remote_setup_io.material_sink',
                                   'okto_nexus_connector.identity.import_flow.read_secret_stdin'],
           'source_hashes': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                             for name in ('protected_pty.py', 'owned_job.py', 'cooperative_producer.py', 'cooperative_consumer.py', 'qualify.py')}}
(OUTPUT / 'qualification.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
