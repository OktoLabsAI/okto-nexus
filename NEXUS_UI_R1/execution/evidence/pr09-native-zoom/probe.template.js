async page => {
 const cfg=__CFG__, checks=[],requests=[],errors=[],consoleErrors=[];
 const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
 const geometry=()=>page.evaluate(()=>({innerWidth,innerHeight,outerWidth,outerHeight,dpr:devicePixelRatio,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth}));
 try {
  await page.addInitScript(()=>{if(location.protocol==='http:'){localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');}});
  await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor();
  const workers=page.context().serviceWorkers();check('own unpacked extension worker loaded',workers.length===1,{workers:workers.map(w=>w.url())});
  const before=await geometry();
  const zoom=await workers[0].evaluate(async origin=>{const tabs=await chrome.tabs.query({url:origin+'/*'});if(tabs.length!==1)throw Error('Own origin must identify one tab');const id=tabs[0].id;const before=await chrome.tabs.getZoom(id);await chrome.tabs.setZoomSettings(id,{mode:'automatic',scope:'per-tab'});await chrome.tabs.setZoom(id,2);return{tabId:id,before,after:await chrome.tabs.getZoom(id),settings:await chrome.tabs.getZoomSettings(id)};},cfg.url);
  await page.waitForTimeout(250);const after=await geometry();
  check('native API zoom200 with physical geometry unchanged',zoom.before===1&&zoom.after===2&&after.outerWidth===before.outerWidth&&after.innerWidth<before.innerWidth&&after.dpr===before.dpr*2,{zoom,before,after});
  check('Home at native200 has no horizontal overflow',after.scrollWidth<=after.clientWidth+1,{geometry:after});
  await page.screenshot({path:cfg.out+'/native200-home.png'});
  const changed=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.url().includes('quick=all')&&r.status()===200);
  await page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'All',exact:true}).click();const groups=(await(await changed).json()).data.items;
  const pair=groups.flatMap(g=>g.children.map(e=>({g,e}))).find(({e})=>e.source_ref.id===cfg.identities.multi_session_source);if(!pair)throw Error('Exact entry absent');
  const group=page.locator(`[data-home-group="${pair.g.id}"]`);const expand=group.getByRole('button',{name:'Expand',exact:true});if(await expand.count())await expand.click();
  const trigger=group.locator(`[data-home-entry="${pair.e.id}"] [data-home-entry-open]`);await trigger.click();
  const dialog=page.getByTestId('home-detail');await dialog.getByRole('region',{name:'Activity context',exact:true}).waitFor();
  const select=dialog.getByRole('combobox',{name:'Choose the exact session',exact:true});await select.waitFor();
  const opts=await select.locator('option').evaluateAll(ns=>ns.map(n=>({value:n.value,text:n.textContent})));const option=opts.find(o=>o.text.includes(cfg.identities.original_session));if(!option)throw Error('Exact session absent');await select.selectOption(option.value);
  await dialog.getByRole('region',{name:'Session execution output',exact:true}).getByText(cfg.identities.original_session,{exact:true}).waitFor();
  const box=await dialog.boundingBox();const close=dialog.getByRole('button',{name:'Close modal',exact:true});await close.scrollIntoViewIfNeeded();
  const hit=await close.evaluate(el=>{const r=el.getBoundingClientRect();const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return hit===el||el.contains(hit);});
  check('exact session panel fits native200 and Close hit-tests',await page.getByRole('dialog').count()===1&&box.x>=-1&&box.x+box.width<=after.innerWidth+1&&hit,{box,hit,geometry:await geometry()});
  await page.screenshot({path:cfg.out+'/native200-exact-panel.png'});await close.click();await dialog.waitFor({state:'detached'});
  check('panel closes and observation stays read-only',requests.every(r=>['GET','HEAD','OPTIONS'].includes(r.method))&&errors.length===0&&consoleErrors.length===0,{errors,consoleErrors});
  return{status:'PASS',checks,requests,errors,consoleErrors,bundle:cfg.bundle};
 }catch(e){await page.screenshot({path:cfg.out+'/failure.png',fullPage:true});return{status:'FAIL',message:e.message,checks,requests,errors,consoleErrors};}
}
