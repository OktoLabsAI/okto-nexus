async page=>{
 const cfg=__CFG__,checks=[],requests=[],errors=[],consoleErrors=[],pages=[];page.setDefaultTimeout(20000);
 page.on('request',r=>requests.push({method:r.method(),url:r.url()}));page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
 const check=(id,name,ok,data={})=>{checks.push({id,name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 const pulse=name=>page.evaluate(async url=>await(await fetch(url)).json(),cfg.url+'/__ui13/'+name);
 const order=()=>page.locator('[data-home-group]').evaluateAll(ns=>ns.map(n=>({group:n.getAttribute('data-home-group'),entries:[...n.querySelectorAll('[data-home-entry]')].map(e=>e.getAttribute('data-home-entry'))})));
 try{
  await page.addInitScript(()=>{if(location.protocol==='http:'){localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');}});
  await page.setViewportSize({width:1440,height:1100});await page.goto(cfg.url);await page.getByTestId('home-follow-up').waitFor();
  const allResponse=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.url().includes('quick=all')&&r.status()===200);await page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'All',exact:true}).click();let all=(await(await allResponse).json()).data;pages.push({phase:'initial',data:all});
  const groupData=all.items.find(g=>g.connection?.binding_id==='binding');const group=page.locator(`[data-home-group="${groupData.id}"]`);await group.getByRole('button',{name:'Expand',exact:true}).click();
  for(let i=0;i<5&&await group.getByRole('button',{name:'Load more items',exact:true}).count();i++){await group.getByRole('button',{name:'Load more items',exact:true}).click();await page.waitForTimeout(350);}
  await group.locator('[data-home-entry-open]').last().waitFor();
  const shown=await group.locator('[data-home-entry]').count(),preDetail=requests.filter(r=>/\/runtime\/sessions\/[^/?]+(?:\/events)?\?/.test(r.url));
  check('T-LIVE-05','many session rows do not start detail or tail observations',shown>=20&&preDetail.length===0,{shown,preDetail});
  const focus=group.locator('[data-home-entry-open]').last();await focus.focus();const stableId=await focus.evaluate(el=>el.closest('[data-home-entry]').getAttribute('data-home-entry'));const before=await order();
  const updated=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.status()===200);const changed=await pulse('priority');const updatedPage=(await(await updated).json()).data;pages.push({phase:'new_priority',data:updatedPage});
  await page.getByRole('button',{name:'Apply updates',exact:true}).waitFor();
  check('T-HOME-06','real priority update retains expanded line order and exact focus until Apply',JSON.stringify(await order())===JSON.stringify(before)&&await page.evaluate(id=>document.activeElement?.closest('[data-home-entry]')?.getAttribute('data-home-entry')===id,stableId)&&updatedPage.items.some(g=>g.children.some(e=>e.kind==='external'&&e.attention_preview.some(o=>o.category==='action_required'))),{before,after:await order(),focusedEntry:stableId,pulse:changed});
  await page.screenshot({path:cfg.out+'/priority-held-focused.png',fullPage:true});
  await page.getByRole('button',{name:'Apply updates',exact:true}).click();await page.getByRole('button',{name:'Apply updates',exact:true}).waitFor({state:'detached'});
  check('T-HOME-06','explicit Apply exposes current priority ordering',JSON.stringify(await order())!==JSON.stringify(before),{afterApply:await order()});
  const passive=group.locator('[data-home-entry-open]').last();await passive.click();const dialog=page.getByTestId('home-detail');await dialog.getByRole('region',{name:'Session execution output',exact:true}).waitFor();await page.waitForTimeout(700);
  const sessionGets=requests.filter(r=>/\/runtime\/sessions\/[^/?]+(?:\/events)?\?/.test(r.url));const sessionIds=[...new Set(sessionGets.map(r=>new URL(r.url).pathname.split('/sessions/')[1].split('/')[0]))];
  check('T-LIVE-05','one open panel observes only its exact session, no tail per row',await page.getByRole('dialog').count()===1&&await page.getByRole('region',{name:'Session execution output',exact:true}).count()===1&&sessionIds.length===1,{sessionGets,sessionIds,shown});
  await dialog.getByRole('button',{name:'Close modal',exact:true}).click();await dialog.waitFor({state:'detached'});
  await page.getByRole('button',{name:'Pause display',exact:true}).click();const pausedBefore=await order();const progressRead=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.status()===200);const progress=await pulse('progress');const latest=(await(await progressRead).json()).data;pages.push({phase:'progress_while_paused',data:latest});await page.getByRole('button',{name:'Apply updates',exact:true}).waitFor();
  check('T-LIVE-06 SUBSET','visual pause buffers canonical reported progress without control mutations',JSON.stringify(await order())===JSON.stringify(pausedBefore)&&progress.pulses.at(-1).state==='working'&&requests.every(r=>r.method==='GET'),{progress,pausedBefore,whilePaused:await order()});
  await page.getByRole('button',{name:'Apply updates',exact:true}).click();await page.getByRole('button',{name:'Apply updates',exact:true}).waitFor({state:'detached'});
  check('T-LIVE-06 SUBSET','explicit Apply resumes display with current canonical page',await page.getByRole('button',{name:'Pause display',exact:true}).isVisible(),{latestRevision:latest.revision});
  check('all','probe read-only and no frontend errors',requests.every(r=>r.method==='GET')&&errors.length===0&&consoleErrors.length===0,{errors,consoleErrors});
  return{status:'PASS',checks,pages,requests,errors,consoleErrors,limits:['T-LIVE-06 real agents/providers not running; canonical own reported-progress pulse only. No decision/draft validation in this round, so full scenario NOT_RUN.']};
 }catch(e){await page.screenshot({path:cfg.out+'/failure.png',fullPage:true});return{status:'FAIL',message:e.message,checks,pages,requests,errors,consoleErrors};}
}
