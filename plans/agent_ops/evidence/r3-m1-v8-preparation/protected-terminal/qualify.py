import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from protected_pty import READY_PREFIX, transfer_once
OUTPUT = ROOT / sys.argv[1]
OUTPUT.mkdir()
reports = []
for mode in ('key-before-handoff', 'marker-absent', 'marker-divergent'):
    case = OUTPUT / mode
    case.mkdir()
    handoff = case / 'handoff.json'
    assert not handoff.exists()
    env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
    env.update(PATH='C:/Python313;C:/Windows/System32', HOME=str(case), USERPROFILE=str(case),
               APPDATA=str(case), LOCALAPPDATA=str(case), TEMP=str(case), TMP=str(case), PYTHONUTF8='1')
    result = transfer_once(
        producer_argv=['C:/Python313/python.exe', '-I', str(ROOT / 'marker_producer.py'), mode, str(handoff)],
        consumer_argv=['C:/Python313/python.exe', '-I', str(ROOT / 'marker_consumer.py'), str(handoff)],
        env=env, consumer_env={**env, 'OKTO_NEXUS_CONNECTER_DAEMON_FG': '1'},
        cwd=case, timeout_seconds=9 if mode == 'marker-absent' else 25, synthetic_probe=True,
        consumer_ready_marker=READY_PREFIX + str(handoff))
    result.update(case=mode, consumer_marker=(case / 'consumer-started.json').exists(),
                  material_received_marker=(case / 'consumer-ack.json').exists(),
                  handoff_exists=handoff.exists(), producer_saw_ack=(case / 'producer-saw-ack.json').exists())
    (OUTPUT / ('result-' + mode + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    assert result['active_job_processes_after'] == 0
    assert result['material_seen_before_ready_marker'] is True
    if mode == 'key-before-handoff':
        assert result['status'] == 'TRANSFERRED_ONCE' and not result['forced_owned_cleanup']
        assert result['consumer_ready_marker_observed'] and result['consumer_start_count'] == 1
        assert result['producer_alive_at_consumer_start'] and result['producer_saw_ack']
        assert result['producer_exit'] == result['consumer_exit'] == 0
        assert result['consumer_material_matches'] and result['handoff_exists']
    else:
        assert result['status'] == 'UNCONFIRMED' and result['possible_effect']
        assert result['consumer_start_count'] == 0 and not result['delivery_attempted']
        assert not result['consumer_marker'] and not result['material_received_marker']
        assert not result['handoff_exists']
        assert result['reason'] == ('TRANSFER_DEADLINE' if mode == 'marker-absent' else 'CONSUMER_READY_MARKER_MISMATCH')
    reports.append(result)
summary = {'status': 'SYNTHETIC_ONLY_PASS', 'case_count': 3, 'cases': reports,
           'product_cli_calls': 0, 'real_credentials': 0, 'providers': 0,
           'installed_functions': ['remote_setup_io.material_sink', 'remote_setup_io.handoff_sink'],
           'limit': 'Only delayed handoff publication/marker gate. No CLI/service/account or full canonical handoff schema validation.',
           'source_hashes': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                             for name in ('protected_pty.py', 'owned_job.py', 'marker_producer.py', 'marker_consumer.py', 'qualify.py')}}
(OUTPUT / 'qualification.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
