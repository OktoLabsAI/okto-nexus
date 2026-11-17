async page => {
  const checks=[],requests=[],errors=[];
  page.setDefaultTimeout(10000);
  page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
  page.on('pageerror',e=>errors.push(e.message));
  const check=(name,ok,data={})=>checks.push({name,status:ok?'PASS':'FAIL',...data});
  const output='NEXUS_UI_R1/execution/evidence/pr07-navigation';
  const nav=()=>page.getByTestId('navigation-sidebar');
  const advanced=async()=>{await nav().getByRole('button',{name:'Advanced',exact:true}).click();await page.getByTestId('advanced-view').waitFor();};
  const crumb=()=>page.getByRole('navigation',{name:'Breadcrumb'}).locator('[aria-current="page"]').innerText();
  const origin=new URL(page.url()).origin;
  try {
    await page.addInitScript(()=>{
      localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');
      localStorage.setItem('okto.nexus.onboarding.completed.v1','true');
      localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
    });
    await page.setViewportSize({width:1440,height:1100});await page.reload();
    await advanced();
    const groups=await page.getByTestId('advanced-view').getByRole('heading',{level:2}).allTextContents();
    check('NAV03 four Advanced groups',groups.length===4,{groups});
    const destinations=await page.getByTestId('advanced-view').locator('button').evaluateAll(ns=>ns.map(n=>n.querySelector('span').textContent));
    check('Memory OFF not advertised',!destinations.includes('Shared memory'),{destinations});
    for(const label of destinations){
      const view=page.getByTestId('advanced-view');
      await view.getByRole('button',{name:new RegExp('^'+label.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'))}).click();
      await page.waitForFunction(label=>document.querySelector('nav[aria-label="Breadcrumb"] [aria-current="page"]')?.textContent===label,label);
      check('NAV03 destination '+label,(await crumb())===label,{headings:await page.locator('main').getByRole('heading').allTextContents()});
      await advanced();
    }
    check('NAV03 sidebar stays compact',await nav().locator('button[data-view]').count()===5);
    await page.screenshot({path:output+'/advanced-all-groups.png',fullPage:true});
    const memory=await page.request.get(origin+'/api/v1/memory?workspace=ws');
    check('Memory OFF canonical direct endpoint refuses',[403,404,409].includes(memory.status()),{http_status:memory.status(),body:await memory.json()});
    for(const label of ['Graph','Artifacts']){
      await nav().getByRole('button',{name:label,exact:true}).click();
      await page.waitForFunction(label=>document.querySelector('nav[aria-label="Breadcrumb"] [aria-current="page"]')?.textContent===label,label);
      const response=page.waitForResponse(r=>r.url().includes('/api/v1/attention?')&&r.status()===200);
      await page.getByRole('button',{name:/^Needs attention\. All projects and Server\./}).click();
      const result=await(await response).json();
      const entries=(result.data??result).items??[];
      await page.getByText('All projects and Server incidents. The project selector does not filter this queue.',{exact:true}).waitFor();
      const url=new URL((await response).url());
      check('NAV08 bell global from '+label,await crumb()==='Needs attention'&&(!url.searchParams.has('workspace_id')||url.searchParams.get('workspace_id')==='all'),
        {queue_url:url.toString(),items:entries.map(x=>({id:x.id,workspace_id:x.workspace_id,kind:x.kind}))});
      await page.screenshot({path:output+'/global-from-'+label.toLowerCase()+'.png',fullPage:true});
    }
    await page.setViewportSize({width:360,height:1000});
    const focusState=()=>page.evaluate(()=>{const e=document.activeElement;return {tag:e?.tagName,label:e?.getAttribute('aria-label')||e?.textContent?.trim().slice(0,80),hidden:!!e?.closest('[aria-hidden="true"]'),visible:!!e?.checkVisibility(),width:document.documentElement.scrollWidth,viewport:innerWidth};});
    for(const label of ['Home','Conversations','Graph','Artifacts','Advanced']){
      const toggle=page.getByTestId('sidebar-toggle');
      if(await toggle.getAttribute('aria-expanded')!=='true')await toggle.click();
      await nav().getByRole('button',{name:label,exact:true}).click();
      await page.waitForFunction(()=>document.getElementById('dashboard-navigation')?.getAttribute('aria-hidden')==='true');
      const focus=await focusState();
      check('NAV12 mobile navigate '+label,await crumb()===label&&await toggle.getAttribute('aria-expanded')==='false'&&!focus.hidden&&focus.width<=360,{focus});
    }
    await page.getByTestId('sidebar-toggle').focus();await page.keyboard.press('Enter');
    await nav().getByRole('button',{name:'Home',exact:true}).focus();await page.keyboard.press('Escape');
    await page.waitForFunction(()=>document.getElementById('dashboard-navigation')?.getAttribute('aria-hidden')==='true');
    const escapeFocus=await focusState();
    check('NAV12 Escape closes with accessible focus',!escapeFocus.hidden&&escapeFocus.visible,{focus:escapeFocus});
    await page.screenshot({path:output+'/mobile-360.png',fullPage:true});
    check('No canonical mutation requested',requests.every(x=>['GET','HEAD','OPTIONS'].includes(x.method)),{mutations:requests.filter(x=>!['GET','HEAD','OPTIONS'].includes(x.method))});
    check('No page runtime errors',errors.length===0,{errors});
    return {status:checks.some(x=>x.status==='FAIL')?'PARTIAL':'PASS',checks,requests,errors,
      limits:['Question was preseeded; no fresh question/SSE arrival was generated.','No generic Memory view URL contract exists in App; direct canonical HTTP feature refusal was tested.','No assistive-technology speech or physical mobile device qualification.']};
  }catch(error){await page.screenshot({path:output+'/failure.png',fullPage:true});return {status:'FAIL',message:error.message,checks,requests,errors};}
}
