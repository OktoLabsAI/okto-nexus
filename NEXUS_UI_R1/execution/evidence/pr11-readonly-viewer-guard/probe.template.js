async page=>{
 const cfg=__CFG__,requests=[],errors=[];page.on('request',r=>requests.push({method:r.method(),url:r.url()}));page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{if(location.protocol==='http:'){localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');}});
 await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor();
 const response=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.url().includes('quick=all')&&r.status()===200);await page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'All',exact:true}).click();
 const groups=(await(await response).json()).data.items;const pair=groups.flatMap(g=>g.children.map(e=>({g,e}))).find(({e})=>e.source_ref.id===cfg.identities.multi_session_source);
 const group=page.locator(`[data-home-group="${pair.g.id}"]`);const expand=group.getByRole('button',{name:'Expand',exact:true});if(await expand.count())await expand.click();await group.locator(`[data-home-entry="${pair.e.id}"] [data-home-entry-open]`).click();
 const dialog=page.getByTestId('home-detail');const select=dialog.getByRole('combobox',{name:'Choose the exact session',exact:true});await select.waitFor();const opts=await select.locator('option').evaluateAll(ns=>ns.map(n=>({value:n.value,text:n.textContent})));await select.selectOption(opts.find(o=>o.text.includes(cfg.identities.original_session)).value);
 const output=dialog.getByRole('region',{name:'Session execution output',exact:true});await output.getByText(cfg.identities.original_session,{exact:true}).waitFor();
 const auto=output.getByRole('checkbox',{name:'Auto-scroll',exact:true});const protectedByAncestor=await auto.evaluate(el=>!!el.closest('[data-modal-passive]'));await auto.click();await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
 const guard=await dialog.getByText('Discard unsaved changes?',{exact:true}).count();await page.screenshot({path:cfg.out+'/auto-scroll-close.png',fullPage:true});
 const result={confirmed:guard===1,protectedByAncestor,guardCount:guard,requests,errors};if(guard)await dialog.getByRole('button',{name:'Discard changes',exact:true}).click();return result;
}
