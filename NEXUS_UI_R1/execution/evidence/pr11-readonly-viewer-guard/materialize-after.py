from pathlib import Path
import json
root=Path(__file__).resolve().parents[4];out=root/'output/playwright/ui11-viewer-guard';ctl=json.loads((out/'control.json').read_text());ready=json.loads((Path(ctl['control'])/'ready.json').read_text())
source=(Path(__file__).parent/'probe.template.js').read_text().split(' const auto=output.getByRole',1)[0]
source+=''' const checks=[];const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 const auto=output.getByRole('checkbox',{name:'Auto-scroll',exact:true});const protectedByAncestor=await auto.evaluate(el=>!!el.closest('[data-modal-passive]'));await auto.click();
 await page.screenshot({path:cfg.out+'/after-auto-scroll-passive.png',fullPage:true});await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.waitFor({state:'detached'});
 check('read-only Auto-scroll followed by Close creates no dirty guard',protectedByAncestor&&await page.getByText('Discard unsaved changes?',{exact:true}).count()===0&&await page.getByRole('dialog').count()===0,{protectedByAncestor});
 await page.getByRole('button',{name:'New request',exact:true}).click();const message=dialog.getByRole('textbox',{name:'Message',exact:true});await message.fill('Own unsent canonical form guard regression');
 const formPassive=await message.evaluate(el=>!!el.closest('[data-modal-passive]'));await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.getByText('Discard unsaved changes?',{exact:true}).waitFor();
 check('edited canonical composer still requires discard',!formPassive&&await dialog.getByText('Discard unsaved changes?',{exact:true}).count()===1,{formPassive});
 await page.screenshot({path:cfg.out+'/after-canonical-form-guard.png',fullPage:true});await dialog.getByRole('button',{name:'Keep editing',exact:true}).click();check('Keep editing preserves exact unsent draft',await message.inputValue()==='Own unsent canonical form guard regression');
 await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.getByRole('button',{name:'Discard changes',exact:true}).click();await dialog.waitFor({state:'detached'});
 const assets=await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src')));
 check('new frozen bundle and no protected action executed',assets.some(x=>x.includes('index-BGONNtiX.js'))&&requests.every(r=>r.method==='GET')&&errors.length===0,{assets,errors});return{status:'PASS',checks,requests,errors};
}
'''
(out/'after-probe.js').write_text(source.replace('__CFG__',json.dumps({'url':ready['url'],'out':out.as_posix(),'identities':ready['identities']})),encoding='utf-8')
