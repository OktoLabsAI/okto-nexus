from pathlib import Path
import json
root=Path(__file__).resolve().parents[4];out=root/'output/playwright/ui13-live-fences';ctl=json.loads((out/'control.json').read_text());ready=json.loads((Path(ctl['control'])/'ready.json').read_text());source=(Path(__file__).parent/'probe.template.js').read_text();header=source.split(' try{',1)[0]
prefix=''' try{
  const all=await page.evaluate(async()=> (await(await fetch('/api/v1/home/entries?workspace_id=ws&quick=all&limit=10&preview=3')).json()).data);
  const groupData=all.items.find(g=>g.connection?.binding_id==='binding');const group=page.locator(`[data-home-group="${groupData.id}"]`);
'''
body='  await group.locator'+source.split('  await group.locator',1)[1]
(out/'continuation-probe.js').write_text((header+prefix+body).replace('__CFG__',json.dumps({'url':ready['url'],'out':out.as_posix(),'identities':ready['identities']})),encoding='utf-8')
