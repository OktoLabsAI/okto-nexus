async page => {
  page.setDefaultTimeout(8000);
  const checks=[],requests=[],responses=[],errors=[],consoleErrors=[];
  page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
  page.on('response',r=>{if(r.url().includes('/api/'))responses.push({url:r.url(),status:r.status()});});
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
  const check=(name,data,ok=true)=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
  const sidebar=()=>page.getByRole('navigation',{name:'Main navigation',exact:true});
  const nav=async id=>{await sidebar().locator(`[data-view="${id}"]`).click();};
  const snap=async name=>page.screenshot({path:`D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/ui-r1-shell/${name}.png`});
  try {
    await page.addInitScript(()=>{if(location.protocol==='http:'){
      localStorage.setItem('okto-nexus-home-operational','disabled');localStorage.setItem('okto-nexus-workspace','home-alpha');
      localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
    }});
    await page.setViewportSize({width:1440,height:1100});await page.goto('http://127.0.0.1:50224');
    await nav('Home');await page.getByTestId('home-overview').waitFor();
    await page.getByTestId('home-overview').getByText('1 need action',{exact:false}).waitFor();
    const ids=await sidebar().locator('[data-view]').evaluateAll(ns=>ns.map(n=>n.getAttribute('data-view')));
    check('T-NAV-01/02 desktop classic Home has four primary IDs and Advanced only',{ids},JSON.stringify(ids)===JSON.stringify(['Home','Meta-harness','Graph','Artifacts','Advanced']));
    const initialBadge=await page.getByTestId('attention-badge').innerText();
    const markerHome=await page.evaluate(()=>localStorage.getItem('okto-nexus-operator-seen'));
    check('Classic Home preserves unread marker and shows scoped vs global summary',{initialBadge,markerHome,scoped:await page.getByTestId('home-overview').innerText()},markerHome===null&&initialBadge.replace('*','')==='4');
    await snap('desktop-home');
    await nav('Advanced');await page.getByTestId('advanced-view').waitFor();
    const groups=await page.getByTestId('advanced-view').getByRole('heading',{level:2}).allTextContents();
    check('T-NAV-03/05 Advanced has four groups and Memory OFF hidden',{groups},groups.length===4&&await page.getByRole('button',{name:'Shared memory',exact:false}).count()===0);
    await page.getByRole('button',{name:'Policies Inspect and configure policy definitions.',exact:true}).click();
    const crumb=await page.getByRole('navigation',{name:'Breadcrumb',exact:true}).innerText();
    check('Advanced destination keeps section selection and three-level breadcrumb',{crumb},crumb.includes('Advanced')&&crumb.includes('Policies and control')&&crumb.includes('Policies')&&await sidebar().locator('[data-view="Advanced"]').getAttribute('aria-current')==='page');
    await nav('Advanced');await snap('desktop-advanced');
    await nav('Graph');await page.getByTestId('global-attention-button').click();
    await page.getByRole('button',{name:'Review approval',exact:true}).first().waitFor();
    check('T-NAV-07/08 Graph opens global queue with two canonical approvals',{badge:await page.getByTestId('attention-badge').innerText(),approvalButtons:await page.getByRole('button',{name:'Review approval',exact:true}).count()},await page.getByRole('button',{name:'Review approval',exact:true}).count()===2);
    const filtered=page.waitForResponse(r=>r.url().includes('/api/v1/attention?')&&r.url().includes('state=resolved')&&r.status()===200);
    await page.getByRole('combobox',{name:'State',exact:true}).selectOption('resolved');await filtered;
    check('Global active badge is independent of resolved queue filter',{badge:await page.getByTestId('attention-badge').innerText()},(await page.getByTestId('attention-badge').innerText()).replace('*','')==='4');
    await page.getByRole('combobox',{name:'State',exact:true}).selectOption('active');
    await page.getByRole('button',{name:'Review approval',exact:true}).first().waitFor();
    await page.getByRole('button',{name:'Review approval',exact:true}).first().click();
    await page.getByRole('region',{name:'Canonical approval',exact:true}).waitFor();
    check('Canonical approval inspector opens passively as one dialog',{dialogs:await page.getByRole('dialog').count()},await page.getByRole('dialog').count()===1);
    await snap('canonical-approval');await page.getByRole('button',{name:'Close modal',exact:true}).click();
    await nav('Home');await page.getByRole('combobox',{name:'Workspace scope',exact:true}).selectOption('home-beta');
    await page.getByTestId('home-overview').getByText('Workspace: home-beta',{exact:false}).waitFor();
    check('Global badge remains global after project switch',{badge:await page.getByTestId('attention-badge').innerText()},(await page.getByTestId('attention-badge').innerText()).replace('*','')==='4');
    await nav('Meta-harness');await page.getByRole('heading',{name:'Conversations',exact:true}).waitFor();
    await page.waitForFunction(()=>localStorage.getItem('okto-nexus-operator-seen')!==null);
    const markerConversation=await page.evaluate(()=>localStorage.getItem('okto-nexus-operator-seen'));
    await nav('Home');check('T-NAV-09 Conversations keeps operator view marker; Home does not advance it',{markerHome,markerConversation,markerAfterHome:await page.evaluate(()=>localStorage.getItem('okto-nexus-operator-seen'))},await page.evaluate(()=>localStorage.getItem('okto-nexus-operator-seen'))===markerConversation);
    await page.setViewportSize({width:360,height:1000});await page.reload();
    await page.getByRole('button',{name:'Expand navigation',exact:true}).waitFor();
    const mobile=[];
    for(const id of ['Home','Meta-harness','Graph','Artifacts','Advanced']) {
      const menu=page.getByRole('button',{name:'Expand navigation',exact:true});await menu.focus();await page.keyboard.press('Enter');
      await sidebar().locator(`[data-view="${id}"]`).focus();await page.keyboard.press('Enter');
      await page.getByRole('button',{name:'Expand navigation',exact:true}).waitFor();
      const state=await page.evaluate(()=>{const e=document.activeElement,r=e.getBoundingClientRect();return {width:innerWidth,scroll:document.documentElement.scrollWidth,activeTag:e.tagName,activeLabel:e.getAttribute('aria-label'),activeVisible:r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'};});
      await menu.focus();const hit=await menu.evaluate(e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.left+r.width/2,r.top+r.height/2));});
      mobile.push({id,...state,menuHitTest:hit});
    }
    check('T-NAV-12 360px keyboard destinations close menu and retain reachable controls',{mobile},mobile.every(x=>x.width===360&&x.scroll<=360&&x.menuHitTest));
    await snap('mobile-advanced');
    check('GET-only browser has no mutations or frontend failures',{mutations:requests.filter(r=>!['GET','HEAD','OPTIONS'].includes(r.method)),errors,consoleErrors},!requests.some(r=>!['GET','HEAD','OPTIONS'].includes(r.method))&&!errors.length&&!consoleErrors.length);
    return {status:'PASS',checks,requests,responses,errors,consoleErrors,bundle:await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src')))};
  } catch(e) {await snap('failure');return {status:'FAIL',message:e.message,checks,requests,responses,errors,consoleErrors};}
  finally {await page.goto('about:blank');}
}
