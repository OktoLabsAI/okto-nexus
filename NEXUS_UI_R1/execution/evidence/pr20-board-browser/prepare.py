"""Prepare a NEW finite fixture; never rewrite a prior qualification cut."""
from pathlib import Path
import hashlib
import json
import tempfile

here = Path(__file__).resolve().parent
root = here.parents[3]
prior = here.parent / 'pr15-human-third-prepare'
pins = json.loads((prior / 'manifest.json').read_text())
bad = [name for name, digest in pins.items() if hashlib.sha256((prior / name).read_bytes()).hexdigest() != digest]
if bad:
    raise RuntimeError('Frozen PR15 mismatch: ' + ', '.join(bad))
(here / 'pr15-manifest-copy.json').write_bytes((prior / 'manifest.json').read_bytes())
source = (prior / 'fixture.py').read_text(encoding='utf-8')
source = source.replace("prefix='nexus-ui043-third-'", "prefix='nexus-ui-board-'")
source = source.replace("identities=seed_result(s,home);configure_inert_catalog(s,patch,home)", "identities=seed_result(s,home);seed_board(s,identities);configure_inert_catalog(s,patch,home)")
source = source.replace("if message['type']=='http.response.start':actions.append({'at':stamp,'type':'http','method':method,'path':path,'status':message['status']})", "if message['type']=='http.response.start':\n                if method=='POST' and path.endswith(('setup:test','setup:finish')):await asyncio.sleep(1.5)\n                actions.append({'at':stamp,'type':'http','method':method,'path':path,'query':scope.get('query_string',b'').decode() if path=='/api/v1/home/target' else '', 'status':message['status']})")
source = source.replace("def main():", (here / 'seed.py').read_text(encoding='utf-8') + '\n\ndef main():')
(here / 'fixture.py').write_text(source, encoding='utf-8')
(here / 'observation_window.py').write_bytes((prior / 'observation_window.py').read_bytes())
out = root / 'output/playwright/ui-board-final'
out.mkdir(parents=True, exist_ok=True)
ctl = Path(tempfile.mkdtemp(prefix='nexus-ui-board-control-'))
(out / 'control.json').write_text(json.dumps({'control': str(ctl), 'out': str(out)}), encoding='utf-8')
print(json.dumps({'control': str(ctl), 'out': str(out), 'prior_entries': len(pins), 'prior_mismatches': bad, 'fixture_sha256': hashlib.sha256((here/'fixture.py').read_bytes()).hexdigest()}))
