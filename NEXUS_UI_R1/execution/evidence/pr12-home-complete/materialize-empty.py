from pathlib import Path
import json
root=Path(__file__).resolve().parents[4];out=root/'output/playwright/ui12-home-complete';ctl=json.loads((out/'control.json').read_text());ready=json.loads((Path(ctl['control'])/'empty-ready.json').read_text())
(out/'empty-probe.js').write_text((Path(__file__).parent/'empty-probe.template.js').read_text().replace('__CFG__',json.dumps({'url':ready['url'],'out':out.as_posix()})),encoding='utf-8')
