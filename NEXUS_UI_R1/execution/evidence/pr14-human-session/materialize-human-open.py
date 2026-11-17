from pathlib import Path
import json
root=Path(__file__).resolve().parents[4];out=root/'output/playwright/ui043-human';ctl=json.loads((out/'control.json').read_text());ready=json.loads((Path(ctl['control'])/'ready-second.json').read_text())
(out/'open-second.js').write_text((Path(__file__).parent/'open.js').read_text().replace('http://127.0.0.1:61381',ready['url']),encoding='utf-8')
print(json.dumps({'url':ready['url'],'authority':ready['decision_authority_times'],'trigger':ready['facilitator_trigger'],'fixture_pid':ready['fixture_pid']}))
