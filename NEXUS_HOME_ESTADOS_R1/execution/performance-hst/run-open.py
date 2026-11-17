"""Sequential required open-workload cuts. Stop on invalid/missing samples."""
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
for variant in ('baseline-v1', 'candidate-v1', 'candidate-v2'):
    command = [sys.executable, '-B', '-X', 'utf8', str(HERE / 'launch-measure.py'),
               '--connections', '100', '--variant', variant, '--workload', 'open']
    code = subprocess.call(command, stdin=subprocess.DEVNULL)
    if code:
        raise SystemExit(code)
    launch = json.loads((HERE / f'measure-open-100-{variant}-launch.json').read_text())
    result = json.loads(Path(launch['output']).read_text())
    if result['status'] != 'MEASURED':
        print('Stopped for diagnosis: missing/invalid samples; no retry.', flush=True)
        raise SystemExit(2)
