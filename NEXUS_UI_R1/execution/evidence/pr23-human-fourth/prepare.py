from pathlib import Path
import hashlib
import json
import tempfile

here=Path(__file__).resolve().parent
root=here.parents[3]
prior=here.parent/'pr15-human-third-prepare'
pins=json.loads((prior/'manifest.json').read_text())
bad=[p for p,h in pins.items() if hashlib.sha256((prior/p).read_bytes()).hexdigest()!=h]
assert not bad,bad
(here/'pr15-manifest-copy.json').write_bytes((prior/'manifest.json').read_bytes())
source=(prior/'fixture.py').read_text(encoding='utf-8').replace("prefix='nexus-ui043-third-'", "prefix='nexus-ui043-fourth-'")
(here/'fixture.py').write_text(source,encoding='utf-8')
(here/'observation_window.py').write_bytes((prior/'observation_window.py').read_bytes())
(here/'watch.py').write_bytes((here.parent/'pr14-human-session/watch.py').read_bytes())
out=root/'output/playwright/ui043-fourth-human'
out.mkdir(parents=True,exist_ok=True)
control=Path(tempfile.mkdtemp(prefix='nexus-ui043-fourth-control-'))
(out/'control.json').write_text(json.dumps({'control':str(control),'out':str(out)}),encoding='utf-8')
print(json.dumps({'control':str(control),'out':str(out),'prior_entries':len(pins),'prior_drift':bad}))
