from pathlib import Path
import json,tempfile
root=Path(__file__).resolve().parents[4];out=root/'output/playwright/ui12-home-complete';out.mkdir(parents=True,exist_ok=True)
ctl=Path(tempfile.mkdtemp(prefix='nexus-ui12-home-complete-'))
(out/'control.json').write_text(json.dumps({'control':str(ctl),'out':str(out)}),encoding='utf-8');print(ctl)
