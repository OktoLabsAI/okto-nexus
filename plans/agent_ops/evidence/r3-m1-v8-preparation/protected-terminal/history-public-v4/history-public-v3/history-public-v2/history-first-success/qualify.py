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
for mode in ('normal', 'ambiguous', 'hang'):
    case = OUTPUT / mode
    case.mkdir()
    env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
    env.update(PATH='C:/Python313;C:/Windows/System32', HOME=str(case), USERPROFILE=str(case),
               APPDATA=str(case), LOCALAPPDATA=str(case), TEMP=str(case), TMP=str(case), PYTHONUTF8='1')
    result = transfer_once(producer_argv=['C:/Python313/python.exe', '-I', str(ROOT / 'producer.py'), mode],
        consumer_argv=['C:/Python313/python.exe', '-I', str(ROOT / 'consumer.py')],
        env=env, cwd=case, timeout_seconds=3 if mode == 'hang' else 15, synthetic_probe=True)
    result['case'] = mode
    result['consumer_started'] = (case / 'consumer-started.json').exists()
    reports.append(result)
    (OUTPUT / ('result-' + mode + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    assert result['active_job_processes_after'] == 0
    if mode == 'normal':
        assert result['status'] == 'TRANSFERRED_ONCE' and result['consumer_material_matches']
    else:
        assert result['status'] == 'UNCONFIRMED' and not result['consumer_started']
summary = {'status': 'SYNTHETIC_ONLY_PASS', 'cases': reports, 'native_product_calls': 0,
           'providers': 0, 'real_credentials': 0,
           'source_hashes': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in ROOT.glob('*.py')}}
(OUTPUT / 'qualification.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
