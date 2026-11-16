from pathlib import Path
import json
root=Path(__file__).resolve().parents[4];out=root/'output/playwright/ui13-live-fences';ctl=json.loads((out/'control.json').read_text());ready=json.loads((Path(ctl['control'])/'ready.json').read_text())
(out/'probe.js').write_text((Path(__file__).parent/'probe.template.js').read_text().replace('__CFG__',json.dumps({'url':ready['url'],'out':out.as_posix(),'identities':ready['identities']})),encoding='utf-8')
