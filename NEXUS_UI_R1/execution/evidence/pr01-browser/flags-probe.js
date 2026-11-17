async page => {
  page.setDefaultTimeout(8000);
  const checks=[],errors=[],consoleErrors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
  page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
  const check=(name,data,ok)=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
  try {
    await page.addInitScript(()=>{if(location.protocol==='http:'){
      localStorage.setItem('okto-nexus-home-operational','disabled');localStorage.setItem('okto-nexus-workspace','home-alpha');
      localStorage.setItem('okto.nexus.onboarding.completed.v1','true');localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
    }});
    await page.setViewportSize({width:1440,height:1100});await page.goto('http://127.0.0.1:64945');
    const nav=page.getByRole('navigation',{name:'Main navigation',exact:true});
    await nav.locator('[data-view="Advanced"]').click();await page.getByTestId('advanced-view').waitFor();
    await page.getByRole('button',{name:/^Shared memory/}).waitFor();
    check('Memory ON remains feature-driven in Advanced index',{visible:await page.getByRole('button',{name:/^Shared memory/}).count()},await page.getByRole('button',{name:/^Shared memory/}).count()===1);
    await page.screenshot({path:'D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/ui-r1-shell/memory-on.png'});
    const bell=page.getByTestId('global-attention-button');const label=await bell.getAttribute('aria-label');
    check('Attention OFF retains globally reachable bell with explicit unavailable count',{label,badge:await page.getByTestId('attention-badge').innerText()},label.includes('disabled')&&await bell.isEnabled()&&await page.getByTestId('attention-badge').innerText()==='!');
    await bell.click();await page.getByRole('button',{name:'Review approvals',exact:true}).waitFor();
    check('Classic fallback provides canonical approval and conversation shortcuts',{approve:await page.getByRole('button',{name:'Review approvals',exact:true}).count(),converse:await page.getByRole('button',{name:'Open Conversations',exact:true}).count()},await page.getByRole('button',{name:'Review approvals',exact:true}).count()===1&&await page.getByRole('button',{name:'Open Conversations',exact:true}).count()===1);
    await page.getByRole('button',{name:'Review approvals',exact:true}).click();await page.getByRole('heading',{name:'Approvals',exact:true}).waitFor();
    await page.getByRole('tab',{name:/^Pending/}).waitFor();
    check('Attention OFF shortcut reaches existing canonical approvals page',{text:await page.locator('main').innerText()},(await page.locator('main').innerText()).toLowerCase().includes('pending'));
    await page.screenshot({path:'D:/Projetos/Techridy/okto_labs_okto_nexus/output/playwright/ui-r1-shell/attention-off-approvals.png'});
    const denied=await page.request.get('http://127.0.0.1:64945/api/v1/approvals?api_key=ui-r1-invalid-qualification-key');
    check('Real canonical HTTP middleware rejects invalid credential on advanced API',{status:denied.status(),body:await denied.json()},denied.status()===401);
    const cross=await page.request.get('http://127.0.0.1:64945/api/v1/approvals',{headers:{Origin:'https://invalid-qualification.example'}});
    checks.push({name:'Real cross-origin operator read response (not delegated-agent ACL test)',status:'OBSERVED',httpStatus:cross.status(),body:await cross.json()});
    check('Flag variant browser performs no mutations and has no frontend errors',{errors,consoleErrors,mutations:requests.filter(r=>!['GET','HEAD','OPTIONS'].includes(r.method))},!errors.length&&!consoleErrors.length&&!requests.some(r=>!['GET','HEAD','OPTIONS'].includes(r.method)));
    return {status:'PASS',checks,requests,errors,consoleErrors};
  }catch(e){return {status:'FAIL',message:e.message,checks,requests,errors,consoleErrors};}
  finally{await page.goto('about:blank');}
}
