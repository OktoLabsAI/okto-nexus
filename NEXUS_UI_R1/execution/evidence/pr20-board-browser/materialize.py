from pathlib import Path
import argparse
import hashlib
import json

p = argparse.ArgumentParser()
p.add_argument('--bundle', required=True)
p.add_argument('--sha256', required=True)
p.add_argument('--css', required=True)
p.add_argument('--css-sha256', required=True)
args = p.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[3]
out = root / 'output/playwright/ui-board-final'
control = Path(json.loads((out / 'control.json').read_text())['control'])
ready = json.loads((control / 'ready.json').read_text())
assets = root / 'src/okto_nexus/adapters/inbound/http/static/assets'
for name, expected in ((args.bundle, args.sha256), (args.css, args.css_sha256)):
    assert hashlib.sha256((assets/name).read_bytes()).hexdigest() == expected, name
paths = ['frontend/src/components/home/OperationalHome.tsx', 'frontend/src/components/home/HomeBoardCards.tsx',
         'frontend/src/components/home/HomeCards.tsx', 'frontend/src/components/onboarding/ProjectConnectFlow.tsx',
         'frontend/src/components/ConnectionWorkflow.tsx', 'frontend/src/homeController.ts', 'frontend/src/homeTypes.ts',
         'frontend/src/homeApi.ts', 'src/okto_nexus/application/home_entries.py',
         'src/okto_nexus/adapters/outbound/sqlite/home_entries.py', 'src/okto_nexus/domain/home_board.py',
         'src/okto_nexus/adapters/inbound/http/static/index.html',
         'src/okto_nexus/adapters/inbound/http/static/assets/' + args.bundle,
         'src/okto_nexus/adapters/inbound/http/static/assets/' + args.css]
pins = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths}
cfg = {'url': ready['url'], 'out': out.as_posix(), 'projectRoot': ready['identities']['project_root'], 'bundle': args.bundle}
script = (here / 'browser.template.js').read_text().replace('__CFG__', json.dumps(cfg))
(out / 'browser.js').write_text(script, encoding='utf-8')
(out / 'runtime-pins.json').write_text(json.dumps(pins, indent=2), encoding='utf-8')
print(json.dumps({'script': str(out/'browser.js'), 'pins': len(pins), 'url': ready['url']}))
