import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ready = json.loads((HERE/'ready.json').read_text(encoding='utf-8'))
config = dict(out='output/playwright/qc05', ids=ready['identities']['public_ids'],
              legacy_binding=ready['identities']['legacy_binding'])
source = (ROOT/'tests/quick_connect/browser_public_ids_checks.js').read_text(encoding='utf-8')
(HERE/'checks-run.js').write_text(source.replace('__CFG__', json.dumps(config)), encoding='utf-8')
source = (ROOT/'tests/quick_connect/browser_public_ids_continuation.js').read_text(encoding='utf-8')
(HERE/'continuation-run.js').write_text(source.replace('__CFG__', json.dumps(config)), encoding='utf-8')
