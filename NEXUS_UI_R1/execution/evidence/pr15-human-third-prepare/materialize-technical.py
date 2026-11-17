from pathlib import Path
import json
here=Path(__file__).resolve().parent;root=here.parents[3];out=root/'output/playwright/ui043-third-technical';ctl=json.loads((out/'control.json').read_text());ready=json.loads((Path(ctl['control'])/'ready.json').read_text());cfg={'url':ready['url'],'out':out.as_posix(),'projectRoot':ready['identities']['project_root'],'bundle':'index-CKlKNFgD.js'}
(out/'technical.js').write_text((here/'technical.template.js').read_text().replace('__CFG__',json.dumps(cfg)),encoding='utf-8')
