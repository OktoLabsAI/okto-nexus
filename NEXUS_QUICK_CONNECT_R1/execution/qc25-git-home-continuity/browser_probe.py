"""Record own Playwright CLI commands without reading cookies or auth state."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
allocation = json.loads((HERE / 'allocation.json').read_text())
root = Path(allocation['root'])
parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['checks', 'requests', 'close', 'snapshot'])
action = parser.parse_args().action
if action == 'checks':
    (REPO / 'output/playwright/qc25').mkdir(parents=True, exist_ok=True)
    (HERE / 'checks.js').write_text((HERE / 'checks-template.js').read_text().replace('__CFG__', json.dumps(allocation)), encoding='utf-8')
    tail = ['run-code', '--filename', str(HERE / 'checks.js')]
else:
    tail = [action]
argv = [shutil.which('rtk'), 'proxy', 'C:/Program Files/nodejs/npx.cmd', '--yes', '--package', '@playwright/cli',
        'playwright-cli', '--session=qc25-git-home', *tail]
result = subprocess.run(argv, cwd=REPO, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', timeout=90)
(root / (action + '-cli.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
(root / (action + '-command.json')).write_text(json.dumps(dict(argv=argv, exit_code=result.returncode), indent=2) + '\n')
if action == 'checks' and '### Result\n' in result.stdout:
    text = result.stdout.split('### Result\n', 1)[1]
    value, _ = json.JSONDecoder().raw_decode(text)
    (root / 'checks-result.json').write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(dict(status=value['status'], checks=value['checks']), ensure_ascii=False))
else:
    print(result.stdout)
raise SystemExit(result.returncode)
