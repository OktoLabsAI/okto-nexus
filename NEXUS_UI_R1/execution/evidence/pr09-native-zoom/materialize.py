from pathlib import Path
import json
root=Path(__file__).resolve().parents[4]
out=root/'output/playwright/ui09-native-zoom'
control=json.loads((out/'control.json').read_text())
ready=json.loads((Path(control['control'])/'ready.json').read_text())
cfg=dict(url=ready['url'],identities=ready['identities'],out=out.as_posix(),bundle='index-BXpHvePH.js')
text=(Path(__file__).parent/'probe.template.js').read_text()
(out/'probe.js').write_text(text.replace('__CFG__',json.dumps(cfg)),encoding='utf-8')
print(out/'probe.js')
