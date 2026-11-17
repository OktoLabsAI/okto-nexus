from pathlib import Path
import json,tempfile,hashlib
here=Path(__file__).resolve().parent;root=here.parents[3];old=here.parent/'pr14-human-session';m=json.loads((old/'manifest.json').read_text());bad=[n for n,h in m.items() if hashlib.sha256((old/n).read_bytes()).hexdigest()!=h]
if bad:raise RuntimeError('Immutable PR14 mismatch:'+','.join(bad))
out=root/'output/playwright/ui043-third-technical';out.mkdir(parents=True,exist_ok=True);ctl=Path(tempfile.mkdtemp(prefix='nexus-ui043-third-tech-'))
(out/'control.json').write_text(json.dumps({'control':str(ctl),'out':str(out)}),encoding='utf-8');print(ctl)
