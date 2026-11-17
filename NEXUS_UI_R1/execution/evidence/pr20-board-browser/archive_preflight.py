from pathlib import Path
import json
import shutil

here = Path(__file__).resolve().parent
root = here.parents[3]
dest = here / 'seed-preflight-antecedent'
dest.mkdir(exist_ok=True)
ctl = Path('C:/Users/jpamb/AppData/Local/Temp/nexus-ui-board-control-uuqtv5f8')
for name in ('ready.json','actions.json','cleanup.json','peer-status.json'):
    shutil.copy2(ctl/name,dest/name)
shutil.copy2(root/'output/playwright/ui-board-final/preflight-board.json',dest/'board.json')
ready=json.loads((dest/'ready.json').read_text())
(dest/'limit.json').write_text(json.dumps({'scope':'Canonical real HTTP preflight only; browser stayed about:blank; zero POST/provider calls.', 'result':'ready, all sources ready, Active29/Needs_you1/Results12', 'limit':'VERIFYING handoffs are watch-only for this loopback operator; did not cover Needs you pagination.', 'fixture_exit_code':0,'fixture_output':'f4b4fe','original_fixture_pid':ready['fixture_pid'],'url':ready['url']},indent=2),encoding='utf-8')
print(json.dumps({'fixture_pid':ready['fixture_pid'],'url':ready['url']}))
