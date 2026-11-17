from pathlib import Path
import json
root=Path(__file__).resolve().parents[4];dest=Path(__file__).parent;out=root/'output/playwright/ui13-live-fences';ctl=json.loads((out/'control.json').read_text());ready=json.loads((Path(ctl['control'])/'ready.json').read_text());source=(dest/'probe.template.js').read_text();header=source.split(' try{',1)[0]
prior=json.loads((dest/'continuation-cli.txt').read_text().split('### Result\n',1)[1].split('\n### Ran',1)[0])
data={'before':prior['checks'][1]['before'],'stableId':prior['checks'][1]['focusedEntry'],'updated':prior['pages'][0]['data']}
prefix=''' try{
  const retained=__RETAINED__,before=retained.before,stableId=retained.stableId;
  const all=retained.updated;const groupData=all.items.find(g=>g.connection?.binding_id==='binding');const group=page.locator(`[data-home-group="${groupData.id}"]`);const shown=await group.locator('[data-home-entry]').count();
  check('T-HOME-06','changed canonical priority preserves expanded order and exact focused line until Apply',JSON.stringify(await order())===JSON.stringify(before)&&await page.evaluate(id=>document.activeElement?.closest('[data-home-entry]')?.getAttribute('data-home-entry')===id,stableId)&&JSON.stringify(all.items.map(g=>g.id))!==JSON.stringify(before.map(g=>g.group)),{before,after:await order(),stableId,canonicalNewOrder:all.items.map(g=>g.id),limit:'Blocked external is watch/configured, not action_required. Canonical priority running2→passive5 changes group order.'});
'''
body='  await page.screenshot({path:cfg.out+\'/priority-held-focused.png\''+source.split("  await page.screenshot({path:cfg.out+'/priority-held-focused.png'",1)[1]
(out/'finish-probe.js').write_text((header+prefix+body).replace('__CFG__',json.dumps({'url':ready['url'],'out':out.as_posix()})).replace('__RETAINED__',json.dumps(data)),encoding='utf-8')
