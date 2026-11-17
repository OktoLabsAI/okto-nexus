from pathlib import Path
import json
here=Path(__file__).resolve().parent;root=here.parents[3];out=root/'output/playwright/ui043-third-human';ctl=json.loads((out/'control.json').read_text());ready=json.loads((Path(ctl['control'])/'ready.json').read_text());source=(here.parent/'pr14-human-session/open.js').read_text();(out/'open.js').write_text(source.replace('http://127.0.0.1:61381',ready['url']),encoding='utf-8');print(json.dumps({'url':ready['url'],'fixture_pid':ready['fixture_pid'],'window_seconds':ready['observation_window_seconds'],'extension':ready['extend_read_window_file']}))
