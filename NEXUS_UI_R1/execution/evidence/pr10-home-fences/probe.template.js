async page=>{
 const cfg=__CFG__,checks=[],requests=[],failed=[],errors=[],consoleErrors=[],envelopes=[];
 page.setDefaultTimeout(15000);
 page.on('request',r=>requests.push({method:r.method(),url:r.url()}));page.on('requestfailed',r=>failed.push({url:r.url(),failure:r.failure()}));
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
 const check=(id,name,ok,data={})=>{checks.push({id,name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
 const control=async name=>page.evaluate(async url=>await(await fetch(url)).json(),cfg.url+'/__ui10/'+name);
 const waitEntries=ws=>page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.url().includes('workspace_id='+ws)&&r.status()===200);
 try{
  await page.addInitScript(()=>{if(location.protocol==='http:'){localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');}});
  await page.setViewportSize({width:1440,height:1100});const init=waitEntries('ws');await page.goto(cfg.url);const first=(await(await init).json()).data;envelopes.push({phase:'A_initial',data:first});await page.getByTestId('home-follow-up').waitFor();
  await control('hold-a');await page.getByRole('button',{name:'Refresh',exact:true}).click();
  let held;for(let i=0;i<100;i++){held=await control('events');if(held.events.some(e=>e.event==='A_canonical_response_buffered'))break;await page.waitForTimeout(100);}
  check('T-HOME-08','genuine A HTTP200 response captured before switching',held.events.some(e=>e.event==='A_canonical_response_buffered'&&e.status===200));
  const switched=waitEntries('ui04-empty');await page.getByRole('combobox',{name:'Workspace scope',exact:true}).selectOption('ui04-empty');const empty=(await(await switched).json()).data;envelopes.push({phase:'B_empty',data:empty});
  await page.getByRole('button',{name:'Connect your first harness',exact:true}).waitFor();const before=await page.getByTestId('home-follow-up').innerText();
  await control('release-a');let released;for(let i=0;i<50;i++){released=await control('events');if(released.events.some(e=>e.event==='A_response_release_attempt'))break;await page.waitForTimeout(100);}await page.waitForTimeout(300);
  check('T-HOME-08','late A release preserves only B scope and empty contents',released.events.some(e=>e.event==='A_response_release_attempt')&&await page.getByRole('combobox',{name:'Workspace scope',exact:true}).inputValue()==='ui04-empty'&&await page.getByTestId('home-follow-up').innerText()===before&&await page.locator('[data-home-group]').count()===0,{before,after:await page.getByTestId('home-follow-up').innerText(),events:released.events});
  check('T-HOME-10','no-occurrence scope has no empty Server or Needs you panel; filter and bell remain',empty.server_attention.total===0&&empty.summary.occurrences.value===0&&await page.getByRole('button',{name:/Server attention/}).count()===0&&await page.getByRole('heading',{name:'Needs you',exact:true}).count()===0&&await page.getByTestId('global-attention-button').isVisible()&&await page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'Needs you',exact:true}).isVisible(),{server_attention:empty.server_attention,occurrences:empty.summary.occurrences});
  await page.screenshot({path:cfg.out+'/B-empty-after-late-A.png',fullPage:true});
  await control('fail-results');const partialResponse=waitEntries('ws');await page.getByRole('combobox',{name:'Workspace scope',exact:true}).selectOption('ws');const partial=(await(await partialResponse).json()).data;envelopes.push({phase:'A_partial_results_failure',data:partial});
  await page.getByText('Some information is incomplete or unavailable. Totals may be unknown; refresh before acting.',{exact:true}).waitFor();
  check('T-HOME-07','isolated results failure keeps valid work and explicit partiality without onboarding',partial.status==='partial'&&partial.source_status.results==='unavailable'&&partial.source_status.work==='ready'&&partial.source_status.connections==='ready'&&partial.items.length>0&&await page.locator('[data-home-group]').count()>0&&await page.getByRole('button',{name:'Connect your first harness',exact:true}).count()===0,{source_status:partial.source_status,status:partial.status,total:partial.total,renderedGroups:await page.locator('[data-home-group]').count(),inventory:partial.inventory});
  await page.screenshot({path:cfg.out+'/partial-results-source.png',fullPage:true});
  check('all','frozen asset and read-only observation without page exceptions',(await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src')))).some(x=>x.includes('index-BXpHvePH.js'))&&requests.every(r=>['GET','HEAD','OPTIONS'].includes(r.method))&&errors.length===0,{errors,consoleErrors,failed});
  return{status:'PASS',checks,envelopes,requests,failed,errors,consoleErrors};
 }catch(e){await page.screenshot({path:cfg.out+'/failure.png',fullPage:true});return{status:'FAIL',message:e.message,checks,envelopes,requests,failed,errors,consoleErrors};}
}
