"""Sequential six remaining mixed cuts; no retry or concurrent worker."""
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
for size in (10, 100):
    for variant in ('baseline-v1', 'candidate-v1', 'candidate-v2'):
        command = [sys.executable, '-B', '-X', 'utf8', str(HERE / 'launch-measure.py'),
                   '--connections', str(size), '--variant', variant]
        code = subprocess.call(command, stdin=subprocess.DEVNULL)
        if code:
            raise SystemExit(code)
        launch = json.loads((HERE / f'measure-{size}-{variant}-launch.json').read_text())
        result = json.loads(Path(launch['output']).read_text())
        if result['status'] != 'MEASURED':
            print('Stopped for diagnosis: missing/invalid measured samples; no retry.', flush=True)
            raise SystemExit(2)
