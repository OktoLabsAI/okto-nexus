async page => {
  const checks=[],requests=[];
  page.setDefaultTimeout(10000);
  page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
  const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
  const nav=()=>page.getByTestId('navigation-sidebar'),toggle=()=>page.getByTestId('sidebar-toggle');
  const state=()=>page.evaluate(()=>{const e=document.activeElement;return {tag:e?.tagName,testid:e?.getAttribute('data-testid'),label:e?.getAttribute('aria-label')||e?.textContent?.trim().slice(0,80),hidden:!!e?.closest('[aria-hidden="true"]'),visible:!!e?.checkVisibility(),width:document.documentElement.scrollWidth};});
  const open=async()=>{if(await toggle().getAttribute('aria-expanded')!=='true')await toggle().click();};
  const closed=()=>page.waitForFunction(()=>document.getElementById('dashboard-navigation')?.getAttribute('aria-hidden')==='true');
  const crumb=()=>page.getByRole('navigation',{name:'Breadcrumb'}).locator('[aria-current="page"]').innerText();
  try {
    await page.addInitScript(()=>{localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');localStorage.setItem('okto-nexus-sidebar','open');localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');});
    await page.setViewportSize({width:360,height:1000});await page.reload();
    const assets=await page.evaluate(()=>({scripts:[...document.scripts].map(x=>x.src),css:[...document.querySelectorAll('link[rel="stylesheet"]')].map(x=>x.href)}));
    check('Exact final JS/CSS served',assets.scripts.some(x=>x.endsWith('index-BXpHvePH.js'))&&assets.css.some(x=>x.endsWith('index-C-ZFb395.css')),{assets});
    const info=await page.request.get(new URL(page.url()).origin+'/api/v1/info');const body=await info.json();
    check('Canonical Server feature_memory false',(body.data??body).features.feature_memory===false);
    for(const label of ['Home','Conversations','Graph','Artifacts','Advanced']){
      await open();await nav().getByRole('button',{name:label,exact:true}).click();await closed();
      const focus=await state();
      check('Mobile route '+label+' closes and restores focus',await crumb()===label&&focus.testid==='sidebar-toggle'&&!focus.hidden&&focus.visible&&focus.width<=360,{focus});
    }
    await open();await page.getByRole('button',{name:/^Needs attention\. All projects and Server\./}).click();await closed();
    const bell=await state();
    check('Sixth global Attention route keeps legitimate bell focus',await crumb()==='Needs attention'&&!bell.hidden&&bell.visible,{focus:bell});
    await open();await nav().getByRole('button',{name:'Home',exact:true}).focus();await page.keyboard.press('Escape');await closed();
    const escape=await state();check('Escape restores controlling trigger',escape.testid==='sidebar-toggle'&&!escape.hidden&&escape.visible,{focus:escape});
    await open();await nav().getByRole('button',{name:'Home',exact:true}).focus();
    await page.getByRole('button',{name:'Close navigation',exact:true}).click({position:{x:350,y:40}});await closed();
    const backdrop=await state();check('Backdrop closes without hidden focus',!backdrop.hidden&&backdrop.visible,{focus:backdrop});
    await open();await page.getByRole('combobox',{name:'Workspace scope'}).focus();await page.keyboard.press('Escape');await closed();
    check('External workspace selector focus is not stolen',await page.getByRole('combobox',{name:'Workspace scope'}).evaluate(e=>document.activeElement===e));
    await page.setViewportSize({width:1440,height:1100});await nav().getByRole('button',{name:'Home',exact:true}).focus();
    await page.setViewportSize({width:360,height:1000});await closed();
    const resized=await state();check('Desktop to narrow resize restores hidden navigation focus',resized.testid==='sidebar-toggle'&&!resized.hidden,{focus:resized});
    await page.screenshot({path:'NEXUS_UI_R1/execution/evidence/pr07-navigation/mobile-focus-final.png',fullPage:true});
    check('No mutation requested',requests.every(x=>['GET','HEAD','OPTIONS'].includes(x.method)));
    return {status:'PASS',checks,requests,limits:['No physical mobile device or assistive-technology speech test.']};
  }catch(error){await page.screenshot({path:'NEXUS_UI_R1/execution/evidence/pr07-navigation/focus-final-failure.png',fullPage:true});return {status:'FAIL',message:error.message,checks,requests};}
}
