// Automated DOM/HTTP qualification only; no screen reader is launched or simulated.
async (page) => {
  page.setDefaultTimeout(60000);
  const origin=new URL(page.url()).origin;
  if(!origin.startsWith('http://127.0.0.1:'))throw Error('Own manual_probe loopback URL required');
  const errors=[],mutations=[],overview=[];
  const request=r=>{if(new URL(r.url()).origin===origin&&!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push({method:r.method(),path:new URL(r.url()).pathname});};
  const failure=e=>errors.push(e.message);
  const response=r=>{if(r.url().includes('/api/v1/home/overview?'))overview.push({status:r.status(),query:new URL(r.url()).search});};
  page.on('request',request);page.on('pageerror',failure);page.on('response',response);
  await page.addInitScript(()=>{
    if(!['http:','https:'].includes(location.protocol))return;
    localStorage.setItem('okto-nexus-home-operational','enabled');
    localStorage.setItem('okto.nexus.onboarding.completed.v1','true');
    localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
    localStorage.setItem('okto-nexus-workspace','home-alpha');
  });
  try{
    await page.reload();await page.getByRole('heading',{name:'Review the integration',exact:true}).waitFor();
    const field=page.getByRole('combobox',{name:'Filter Home by agent'});
    await field.fill('A');await field.focus();await field.evaluate(el=>el.setSelectionRange(0,1));
    const baseline=await page.locator('section[aria-label="Work"] [data-home-item]').evaluateAll(ns=>ns.map(n=>n.getAttribute('data-home-item')));
    await page.evaluate(()=>{
      const live=document.querySelector('p[aria-live="polite"][aria-atomic="true"]');
      if(!live)throw Error('Actual Home live region missing');
      window.__manualProbeAnnouncements=[];
      window.__manualProbeObserver=new MutationObserver(()=>{
        const text=live.textContent.trim();
        if(text)window.__manualProbeAnnouncements.push({text,at:performance.now()});
      });
      window.__manualProbeObserver.observe(live,{childList:true,characterData:true,subtree:true});
    });
    await page.waitForFunction(()=>window.__manualProbeAnnouncements.length>=2,null,{timeout:50000});
    await page.getByRole('heading',{name:'Screen reader probe 1',exact:true}).waitFor();
    await page.getByRole('heading',{name:'Screen reader probe 2',exact:true}).waitFor();
    const announcements=await page.evaluate(()=>window.__manualProbeAnnouncements);
    const state=await field.evaluate(el=>({value:el.value,focused:el===document.activeElement,selection:[el.selectionStart,el.selectionEnd]}));
    const after=await page.locator('section[aria-label="Work"] [data-home-item]').evaluateAll(ns=>ns.map(n=>n.getAttribute('data-home-item')));
    const novel=after.filter(id=>!baseline.includes(id));
    if(announcements.length!==2||announcements.some(x=>x.text!=='Home updated. New work, attention or results are available.'))throw Error('Announcements were not two grouped Home summaries');
    if(novel.length!==2||new Set(novel).size!==2)throw Error('Expected two actual new canonical Work identities');
    if(!state.focused||state.value!=='A'||state.selection.join(',')!=='0,1')throw Error('Real refresh moved focus or selection');
    if(mutations.length||errors.length)throw Error('Unexpected mutation or page error');
    const counters=await page.locator('[aria-label="Operational summary"]').innerText();
    if(!counters.includes('Running\n0'))throw Error('Probe must not fabricate native running');
    const result={status:'PASS',qualificationLayer:'DOM and real HTTP only',spokenAssistiveTechnologyStatus:'NOT_RUN',narratorLaunched:false,
      announcements,novelWorkIds:novel,focus:state,overviewRequests:overview,mutationRequests:mutations,pageErrors:errors,counters,
      bundle:await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src'))),limits:['Two real SQLite handoff/task/event pulses; no DOM payload injection or routed GET response.','No actual assistive-technology consumption or human speech observation was performed.']};
    await page.evaluate(value=>localStorage.setItem('home-r1-manual-at-dom-evidence',JSON.stringify(value)),result);
    return result;
  }finally{
    await page.evaluate(()=>window.__manualProbeObserver?.disconnect());
    page.off('request',request);page.off('pageerror',failure);page.off('response',response);
  }
}
