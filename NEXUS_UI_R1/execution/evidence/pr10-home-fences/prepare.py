from pathlib import Path
import tempfile,json
root=Path(__file__).resolve().parents[4]
out=root/'output/playwright/ui10-home-fences';out.mkdir(parents=True,exist_ok=True)
control=Path(tempfile.mkdtemp(prefix='nexus-ui10-home-fences-'))
(out/'control.json').write_text(json.dumps({'control':str(control),'out':str(out)}),encoding='utf-8')
print(control)
