// One cache-disabled preview sample over the standard read-only synthetic fixture.
async (page) => {
  const fixtureUrl='http://127.0.0.1:64454';
  const origin=new URL(fixtureUrl).origin,errors=[],consoleErrors=[],mutations=[],overviewRequests=[];
  page.setDefaultTimeout(10000);
  const onError=e=>errors.push(e.message);
  const onConsole=m=>{if(m.type()==='error')consoleErrors.push(m.text());};
  const onRequest=r=>{if(new URL(r.url()).origin===origin&&!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push({method:r.method(),path:new URL(r.url()).pathname});};
  const onFinished=async r=>{
    if(r.url().includes('/api/v1/home/overview?')){
      const response=await r.response();
      overviewRequests.push({path:new URL(r.url()).pathname,query:new URL(r.url()).search,status:response?.status(),timing:r.timing()});
    }
  };
  page.on('pageerror',onError);page.on('console',onConsole);page.on('request',onRequest);page.on('requestfinished',onFinished);
  const cdp=await page.context().newCDPSession(page);
  try{
    await page.setViewportSize({width:1440,height:1100});
    await cdp.send('Network.enable');await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});await cdp.send('Network.clearBrowserCache');
    await page.addInitScript(()=>{
      if(!['http:','https:'].includes(location.protocol))return;
      localStorage.setItem('okto-nexus-home-operational','enabled');
      localStorage.setItem('okto.nexus.onboarding.completed.v1','true');
      localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
      localStorage.setItem('okto-nexus-workspace','home-alpha');
      window.__humanPreviewFirstWorkDOM=null;window.__humanPreviewFirstWorkFrame=null;
      const observer=new MutationObserver(()=>{
        if(window.__humanPreviewFirstWorkDOM!==null)return;
        const row=document.querySelector('section[aria-label="Work"] [data-home-item] h3');
        if(!row||!row.getBoundingClientRect().height)return;
        window.__humanPreviewFirstWorkDOM={at:performance.now(),title:row.textContent};observer.disconnect();
        requestAnimationFrame(()=>requestAnimationFrame(()=>{window.__humanPreviewFirstWorkFrame=performance.now();}));
      });
      observer.observe(document,{childList:true,subtree:true});
    });
    const responsePromise=page.waitForResponse(r=>r.url().includes('/api/v1/home/overview?workspace_id=home-alpha')&&r.status()===200);
    await page.goto(fixtureUrl,{waitUntil:'domcontentloaded'});
    const response=await responsePromise,dto=(await response.json()).data;
    await page.getByRole('heading',{name:'Review the integration',exact:true}).waitFor();
    await page.waitForFunction(()=>window.__humanPreviewFirstWorkFrame!==null);
    const firstFold=await page.locator('[data-testid="operational-home"]').evaluate(el=>{
      const box=node=>{const r=node.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height,inViewport:r.bottom>0&&r.top<innerHeight,fullyInViewport:r.top>=0&&r.bottom<=innerHeight};};
      const rows=label=>[...el.querySelectorAll(`section[aria-label="${label}"] [data-home-item]`)].map(row=>({id:row.getAttribute('data-home-item'),title:row.querySelector('h3')?.textContent,text:row.innerText,box:box(row)}));
      const dl=el.querySelector('[aria-label="Operational summary"]');
      return {viewport:{width:innerWidth,height:innerHeight},counters:[...dl.children].map(div=>({label:div.querySelector('dt').textContent,value:div.querySelector('dd').textContent,text:div.innerText,box:box(div)})),
        work:rows('Work'),results:rows('Results'),needsYou:{text:el.querySelector('section[aria-label="Needs you"]').innerText,box:box(el.querySelector('section[aria-label="Needs you"]'))},
        server:{text:el.querySelector('section[aria-label="Server"]').innerText,box:box(el.querySelector('section[aria-label="Server"]'))},
        documentWidth:document.documentElement.scrollWidth,contentWidth:el.clientWidth};
    });
    const performanceSample=await page.evaluate(()=>({sampleCount:1,httpCacheDisabled:true,firstWorkDOM:window.__humanPreviewFirstWorkDOM,firstUsefulFrameOpportunityMs:window.__humanPreviewFirstWorkFrame,
      homeResources:performance.getEntriesByType('resource').filter(e=>e.name.includes('/api/v1/home/overview?')).map(e=>({path:new URL(e.name).pathname,query:new URL(e.name).search,startTimeMs:e.startTime,responseEndMs:e.responseEnd,durationMs:e.duration,transferSize:e.transferSize,encodedBodySize:e.encodedBodySize,decodedBodySize:e.decodedBodySize})),
      navigation:performance.getEntriesByType('navigation').map(e=>({startTimeMs:e.startTime,domContentLoadedMs:e.domContentLoadedEventEnd,transferSize:e.transferSize}))}));
    await page.screenshot({path:'D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/home-human-preview/first-fold.png'});
    await page.screenshot({path:'D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/home-human-preview/full-page.png',fullPage:true});
    const scrollers=()=>page.locator('main,[data-testid="operational-home"]').evaluateAll(nodes=>nodes.map(n=>({tag:n.tagName,clientHeight:n.clientHeight,scrollHeight:n.scrollHeight,scrollTop:n.scrollTop})));
    const scrollBefore=await scrollers();await page.mouse.move(1300,850);await page.mouse.wheel(0,450);
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const scrollAfter=await scrollers();
    await page.screenshot({path:'D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/home-human-preview/work-and-result.png'});
    if(errors.length||consoleErrors.length||mutations.length)throw Error('Preview produced unexpected errors/mutations: '+JSON.stringify({errors,consoleErrors,mutations}));
    if(dto.summary.running.value!==0||dto.scope.workspace_id!=='home-alpha')throw Error('Standard fixture scope or actual Running0 changed');
    const result={status:'PASS',humanAssessmentPerformed:false,tenSecondHumanAssessment:'NOT_RUN',captureProvenance:{attempt:2,completeSamplesRetained:1,priorAttempt:{toolRef:'02e443',status:'PASS_WITH_TRUNCATED_CLI_OUTPUT',timingsRetained:false}},source:'Standard browser_fixture.py, no contract Server injection or modified seed data',scope:dto.scope,
      canonical:{summary:dto.summary,workTotal:dto.work.total,attentionTotal:dto.attention.total,resultTotal:dto.results.total,serverAttentionTotal:dto.server_attention.total,
        work:dto.work.items.map(x=>({id:x.id,title:x.title,state:x.display_state,agentIds:x.agent_ids})),results:dto.results.items.map(x=>({id:x.id,title:x.title,outcome:x.outcome,viewState:x.view_state}))},
      firstFold,performanceSample,overviewRequests,scroll:{before:scrollBefore,after:scrollAfter},pageErrors:errors,consoleErrors,mutationRequests:mutations,
      bundle:await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src'))),limitations:['One complete cache-disabled navigation sample retained after an earlier truncated-output capture; not p95 or a controlled cold OS/SQLite-cache benchmark.','The DOM mark and two subsequent animation frames indicate render/frame opportunities, not human comprehension or a physical-paint measurement.','No human participant was simulated. Running0 and Claimed remain distinct.']};
    await page.evaluate(value=>localStorage.setItem('home-r1-human-preview-evidence',JSON.stringify(value)),result);
    return result;
  }finally{
    page.off('pageerror',onError);page.off('console',onConsole);page.off('request',onRequest);page.off('requestfinished',onFinished);
    await cdp.send('Network.setCacheDisabled',{cacheDisabled:false});await cdp.detach();await page.goto('about:blank');
  }
}
