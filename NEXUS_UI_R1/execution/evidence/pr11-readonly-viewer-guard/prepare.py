from pathlib import Path
import tempfile,json
root=Path(__file__).resolve().parents[4];out=root/'output/playwright/ui11-viewer-guard';out.mkdir(parents=True,exist_ok=True)
ctl=Path(tempfile.mkdtemp(prefix='nexus-ui11-viewer-guard-'))
(out/'control.json').write_text(json.dumps({'control':str(ctl),'out':str(out)}),encoding='utf-8');print(ctl)
