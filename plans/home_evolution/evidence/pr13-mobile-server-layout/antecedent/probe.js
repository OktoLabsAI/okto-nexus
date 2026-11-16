// Read-only focal for the current A08 Server lane at desktop and360CSS pixels.
async (page) => {
  const url='http://127.0.0.1:59226',origin=new URL(url).origin;
  const checks=[],errors=[],consoleErrors=[],mutations=[];
  const onRequest=r=>{if(new URL(r.url()).origin===origin&&!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push(r.method());};
  const onError=e=>errors.push(e.message),onConsole=m=>{if(m.type()==='error')consoleErrors.push(m.text());};
  page.on('request',onRequest);page.on('pageerror',onError);page.on('console',onConsole);
  page.setDefaultTimeout(10000);
  await page.addInitScript(()=>{
    if(!['http:','https:'].includes(location.protocol))return;
    localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','home-alpha');
    localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
  });
  const assert=(ok,message)=>{if(!ok)throw Error(message);};
  const server=()=>page.getByRole('region',{name:'Server',exact:true});
  const ids=()=>server().locator('[data-home-item]').evaluateAll(ns=>ns.map(n=>n.getAttribute('data-home-item')));
  const layout=()=>page.locator('[data-testid="operational-home"]').evaluate(el=>{
    const s=el.querySelector('section[aria-label="Server"]'),r=s.getBoundingClientRect();
    return {viewport:innerWidth,documentClient:document.documentElement.clientWidth,documentScroll:document.documentElement.scrollWidth,
      homeClient:el.clientWidth,homeScroll:el.scrollWidth,scrollX,server:{left:r.left,right:r.right,width:r.width,scrollWidth:s.scrollWidth,clientWidth:s.clientWidth},route:location.pathname};
  });
  const within=value=>assert(value.documentScroll<=value.viewport&&value.homeScroll<=value.homeClient&&value.server.scrollWidth<=value.server.clientWidth&&value.server.left>=-1&&value.server.right<=value.viewport+1&&value.scrollX===0,'Horizontal overflow or horizontal scrolling required');
  const actionGeometry=async()=>{
    const seen=server().getByRole('button',{name:'Mark seen',exact:true}).first();
    await seen.focus();assert(!await seen.isDisabled(),'Fresh viewing action disabled');
    await page.keyboard.press('Tab');
    return page.evaluate(()=>{const e=document.activeElement,r=e.getBoundingClientRect();return {text:e.textContent.trim(),left:r.left,right:r.right,top:r.top,bottom:r.bottom,viewportWidth:innerWidth,viewportHeight:innerHeight,enabled:!e.disabled};});
  };
  try{
    await page.setViewportSize({width:1440,height:1100});await page.goto(url);
    await server().waitFor();await page.getByRole('heading',{name:'Review the integration',exact:true}).waitFor();
    let value=await layout();within(value);assert((await ids()).length===3,'Expected three Server previews');
    checks.push({name:'Current desktop Home route exposes separate Server lane',status:'PASS',layout:value,previewIds:await ids()});
    await page.screenshot({path:'D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/home-mobile-server/desktop.png'});
    await page.setViewportSize({width:360,height:1000});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    value=await layout();within(value);
    let action=await actionGeometry();
    assert(action.text.includes('Snooze')&&action.enabled&&action.left>=0&&action.right<=360&&action.top>=0&&action.bottom<=1000,'Keyboard viewing action is clipped or unreachable');
    checks.push({name:'360px Server content and keyboard viewing controls fit without horizontal overflow',status:'PASS',layout:value,keyboardAction:action});
    await page.screenshot({path:'D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/home-mobile-server/mobile-server.png'});
    const response=page.waitForResponse(r=>r.url().includes('/api/v1/home/server-attention?')&&r.status()===200);
    await server().getByRole('button',{name:'Load more server',exact:true}).click();await response;
    const pagedIds=await ids();assert(pagedIds.length===6&&new Set(pagedIds).size===6,'Server pagination lost or duplicated canonical IDs');
    await server().getByRole('button',{name:'Snooze 1 hour',exact:true}).last().focus();
    value=await layout();within(value);
    const last=await server().getByRole('button',{name:'Snooze 1 hour',exact:true}).last().boundingBox();
    assert(last.x>=0&&last.x+last.width<=361&&last.y>=0&&last.y+last.height<=1001,'Last paged control cannot be brought into view');
    checks.push({name:'360px real Server paging remains independent and last-row actions accessible',status:'PASS',layout:value,pagedIds,lastAction:last});
    const scope=page.getByRole('combobox',{name:'Workspace scope'});
    const quiet=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview?workspace_id=home-quiet')&&r.status()===200);
    await scope.selectOption('home-quiet');await quiet;
    await page.getByRole('heading',{name:'Set up your first agent',exact:true}).waitFor();
    assert((await ids()).length===3,'Quiet project hid independent Server previews');
    assert(await page.locator('[aria-label="Operational summary"]').count()===0,'Server items inflated quiet-project counters');
    value=await layout();within(value);action=await actionGeometry();
    assert(action.text.includes('Snooze')&&action.left>=0&&action.right<=360&&action.top>=0&&action.bottom<=1000,'Quiet Server action inaccessible');
    await page.getByRole('heading',{name:'Set up your first agent',exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:'D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/home-mobile-server/mobile-quiet.png'});
    checks.push({name:'360px quiet project keeps setup flow and independent Server lane on same Home route',status:'PASS',layout:value,keyboardAction:action,quietWelcome:true,projectCounterGridAbsent:true});
    assert(!errors.length&&!consoleErrors.length&&!mutations.length,'Unexpected browser error or mutation');
    return {status:'PASS',checks,pageErrors:errors,consoleErrors,mutationRequests:mutations,bundle:await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src'))),limits:['Pre-authorized domain query-port Server occurrences, not a new live global producer or NULL DB insertion.','360CSS-pixel viewport in own headless Chrome; desktop1440 also checked. This does not add a new native200percent zoom or real speech claim.','Viewing controls were focused/reached, not submitted. All exercised requests were GETs.']};
  }finally{
    page.off('request',onRequest);page.off('pageerror',onError);page.off('console',onConsole);await page.goto('about:blank');
  }
}
