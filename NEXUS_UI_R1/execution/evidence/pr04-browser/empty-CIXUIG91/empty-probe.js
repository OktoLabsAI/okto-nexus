async page=>{
  const cfg=__FIXTURE_CONFIG__,checks=[],requests=[],responses=[],errors=[],consoleErrors=[];
  page.setDefaultTimeout(10000);
  page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
  page.on('response',r=>responses.push({status:r.status(),url:r.url()}));
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
  const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
  try{
    await page.addInitScript(()=>{if(location.protocol==='http:'){localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ui04-empty');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');}});
    await page.setViewportSize({width:1440,height:1100});
    const initial=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.url().includes('workspace_id=ui04-empty')&&r.status()===200);
    await page.goto(cfg.url);const envelope=(await(await initial).json()).data;
    await page.getByRole('button',{name:'Connect your first harness',exact:true}).waitFor();
    check('frozen empty Home is backed by exact pre-filter inventory0',envelope.status==='ready'&&envelope.total===0&&envelope.total_is_exact&&envelope.inventory.connections.value===0&&envelope.inventory.connections.total_is_exact,{envelope});
    check('T-HOME03 one first-harness CTA, New request disabled',await page.getByRole('button',{name:'Connect your first harness',exact:true}).count()===1&&await page.getByRole('button',{name:'New request',exact:true}).isDisabled()&&await page.getByRole('button',{name:'Connect agent',exact:true}).count()===0);
    await page.screenshot({path:`${cfg.outputDirectory}/canonical-empty-first-harness.png`,fullPage:true});
    const switching=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.url().includes('workspace_id=ws')&&r.status()===200);
    await page.getByRole('combobox',{name:'Workspace scope',exact:true}).selectOption('ws');const existing=(await(await switching).json()).data;
    await page.getByTestId('home-follow-up').getByRole('heading',{name:'Follow-up',exact:true}).waitFor();
    await page.getByText('Filter details',{exact:true}).click();
    await page.getByLabel('Harness',{exact:true}).fill('ui04-no-such-harness');
    const filtered=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.url().includes('harness=ui04-no-such-harness')&&r.status()===200);
    await page.getByRole('button',{name:'Apply details',exact:true}).click();const after=(await(await filtered).json()).data;
    await page.getByText('No matching activity for these filters.',{exact:true}).waitFor();
    check('existing canonical connections survive filtered total0 without onboarding',existing.inventory.connections.value>0&&after.total===0&&after.inventory.connections.value===existing.inventory.connections.value&&await page.getByRole('button',{name:'Connect your first harness',exact:true}).count()===0&&await page.getByRole('button',{name:'New request',exact:true}).isEnabled(),{beforeInventory:existing.inventory,filteredInventory:after.inventory,filteredTotal:after.total});
    await page.screenshot({path:`${cfg.outputDirectory}/filtered-empty-existing-connections.png`,fullPage:true});
    check('cut JS is exactly current frozen asset',(await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src')))).some(src=>src.includes(cfg.bundle)));
    check('empty qualification is read-only and has no frontend exceptions',requests.every(r=>['GET','HEAD','OPTIONS'].includes(r.method))&&errors.length===0&&consoleErrors.length===0,{errors,consoleErrors});
    return{status:'PASS',checks,requests,responses,errors,consoleErrors,bundle:cfg.bundle,scope:'canonical empty workspace and existing-connection filtered empty only; no native/provider action'};
  }catch(e){await page.screenshot({path:`${cfg.outputDirectory}/empty-failure.png`,fullPage:true});return{status:'FAIL',message:e.message,checks,requests,responses,errors,consoleErrors};}
  finally{await page.goto('about:blank');}
}
