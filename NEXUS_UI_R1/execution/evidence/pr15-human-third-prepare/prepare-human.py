from pathlib import Path
import tempfile,json,hashlib
here=Path(__file__).resolve().parent;root=here.parents[3];old=here.parent/'pr14-human-session';pins=json.loads((old/'manifest.json').read_text());bad=[n for n,h in pins.items() if hashlib.sha256((old/n).read_bytes()).hexdigest()!=h]
if bad:raise RuntimeError('Immutable prior journey mismatch:'+','.join(bad))
out=root/'output/playwright/ui043-third-human';out.mkdir(parents=True,exist_ok=True);ctl=Path(tempfile.mkdtemp(prefix='nexus-ui043-third-human-control-'));(out/'control.json').write_text(json.dumps({'control':str(ctl),'out':str(out)}),encoding='utf-8');print(ctl)
