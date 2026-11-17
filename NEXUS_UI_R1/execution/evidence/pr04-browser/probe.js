async page => {
  // Orchestrator substitutes READY JSON only after Root freezes the exact build.
  const cfg=__FIXTURE_CONFIG__;
  const checks=[],requests=[],responses=[],pageErrors=[],consoleErrors=[];
  page.setDefaultTimeout(10000);
  page.on('request',r=>requests.push({method:r.method(),url:r.url()}));
  page.on('response',r=>{if(r.url().includes('/api/')||r.url().includes('/v1/'))responses.push({url:r.url(),status:r.status()});});
  page.on('pageerror',e=>pageErrors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
  page.on('dialog',d=>{if(d.type()==='beforeunload')void d.accept();});
  const check=(name,ok,data={})=>{checks.push({name,status:ok?'PASS':'FAIL',...data});if(!ok)throw Error(name);};
  const shot=async name=>page.screenshot({path:`${cfg.outputDirectory}/${name}.png`,fullPage:true});
  const dialog=()=>page.getByTestId('home-detail');
  const output=()=>dialog().getByRole('region',{name:'Session execution output',exact:true});
  const close=async()=>{await dialog().getByRole('button',{name:'Close modal',exact:true}).click();await dialog().waitFor({state:'detached'});};
  let groups=[];
  const entrySource=id=>groups.flatMap(g=>g.children.map(e=>({g,e}))).find(({e})=>e.source_ref.id===id);
  const entrySession=id=>groups.flatMap(g=>g.children.map(e=>({g,e}))).find(({e})=>e.kind==='session'&&e.target?.session_id===id);
  const open=async pair=>{
    if(!pair)throw Error('Required exact fixture entry absent from current canonical page');
    const group=page.locator(`[data-home-group="${pair.g.id}"]`);
    const expand=group.getByRole('button',{name:'Expand',exact:true});
    if(await expand.count())await expand.click();
    const trigger=group.locator(`[data-home-entry="${pair.e.id}"] [data-home-entry-open]`);
    await trigger.focus();await trigger.click();await dialog().waitFor();
    await dialog().getByRole('region',{name:'Activity context',exact:true}).waitFor();
    return trigger;
  };
  try {
    await page.addInitScript(()=>{if(location.protocol==='http:'){
      localStorage.setItem('okto-nexus-home-operational','enabled');localStorage.setItem('okto-nexus-workspace','ws');
      localStorage.setItem('okto.nexus.onboarding.completed.v1','true');
      localStorage.setItem('okto-nexus:metrics-opt-in-prompt-dismissed:1.0.0','test');
    }});
    await page.setViewportSize({width:1440,height:1100});await page.goto(cfg.url);
    await page.getByTestId('home-follow-up').waitFor();
    const changed=page.waitForResponse(r=>r.url().includes('/api/v1/home/entries?')&&r.url().includes('quick=all')&&r.status()===200);
    await page.getByRole('group',{name:'Follow-up filter',exact:true}).getByRole('button',{name:'All',exact:true}).click();
    const body=await(await changed).json();groups=body.data.items;
    check('exact frozen JS loaded',(await page.locator('script[src]').evaluateAll(ns=>ns.map(n=>n.getAttribute('src')))).some(x=>x.includes(cfg.expectedBundle)));
    check('single primary Follow-up region',await page.getByTestId('home-follow-up').count()===1);
    await shot('desktop-home');
    const multi=entrySource(cfg.identities.multi_session_source);
    const origin=await open(multi);
    const choose=dialog().getByRole('combobox',{name:'Choose the exact session',exact:true});
    await choose.waitFor();
    check('multi-session activity starts without latest heuristic',(await choose.inputValue())===''&&await output().count()===0,
      {sessions:await choose.locator('option').allTextContents()});
    const options=await choose.locator('option').evaluateAll(ns=>ns.map(n=>({value:n.value,text:n.textContent})));
    for(const sid of [cfg.identities.original_session,cfg.identities.second_session]){
      const option=options.find(o=>o.text.includes(sid));if(!option)throw Error('Exact expected session missing');
      await choose.selectOption(option.value);
      check('passive session selection creates no dirty guard',await dialog().getByText('Discard unsaved changes?',{exact:true}).count()===0,{session:sid});
      await output().getByText(sid,{exact:true}).waitFor();
      check('one output and one dialog for exact session',await output().count()===1&&await page.getByRole('dialog').count()===1,{session:sid});
    }
    await output().getByRole('button',{name:'History',exact:true}).click();
    await shot('desktop-exact-session-history');
    check('live Home display pauses while context is open',await page.getByText('Display updates paused. Agents keep running; decisions require a fresh canonical review.',{exact:true}).count()===1);
    await close();
    check('close restores opening control focus',await origin.evaluate(e=>document.activeElement===e));
    const noTurn=entrySession(cfg.identities.no_turn_session);
    await open(noTurn);await output().getByText(cfg.identities.no_turn_session,{exact:true}).waitFor();
    check('no-turn exact session has one passive output and one dialog',await output().count()===1&&await page.getByRole('dialog').count()===1,
      {target:noTurn.e.target});
    await shot('no-turn-session');await close();
    checks.push({name:'human native question dirty session switch',status:'NOT_RUN',reason:'Shared canonical fixture produces agent-origin question addressed to subject; recipient was not rewritten to fabricate human controls.'});
    await page.getByRole('button',{name:'New request',exact:true}).click();
    const form=dialog().getByRole('textbox',{name:'Message',exact:true});
    await form.fill('own unsent UI04 draft');
    await page.keyboard.press('Escape');
    await dialog().getByText('Discard unsaved changes?',{exact:true}).waitFor();
    await dialog().getByRole('button',{name:'Keep editing',exact:true}).click();
    check('Escape dirty guard keeps real composer draft',(await form.inputValue())==='own unsent UI04 draft');
    await dialog().getByRole('button',{name:'Close modal',exact:true}).click();
    await dialog().getByText('Discard unsaved changes?',{exact:true}).waitFor();
    await shot('composer-dirty-guard');
    await dialog().getByRole('button',{name:'Discard changes',exact:true}).click();
    await dialog().waitFor({state:'detached'});
    check('explicit discard closes unsent composer without mutation',await page.getByRole('dialog').count()===0);
    await page.setViewportSize({width:360,height:1000});
    await open(multi);await choose.waitFor();
    const original=options.find(o=>o.text.includes(cfg.identities.original_session));await choose.selectOption(original.value);
    await output().getByText(cfg.identities.original_session,{exact:true}).waitFor();
    const geometry=await dialog().evaluate(e=>{const r=e.getBoundingClientRect();return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
      dialogWidth:r.width,bodyWidth:e.querySelector('.agent-modal-body').clientWidth,bodyScroll:e.querySelector('.agent-modal-body').scrollWidth};});
    const closeButton=dialog().getByRole('button',{name:'Close modal',exact:true});
    await closeButton.focus();
    const hit=await closeButton.evaluate(e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.left+r.width/2,r.top+r.height/2));});
    check('360px panel retains horizontal layout and reachable close',geometry.documentWidth<=360&&geometry.dialogWidth<=360&&geometry.bodyScroll<=geometry.bodyWidth+1&&hit,{geometry,hit});
    await shot('mobile-exact-session');await close();
    // Additional dirty-draft, real-403, agent-origin and native-zoom cases are
    // separate final-cut probes after current selectors/capabilities are known.
    check('read-only browser made no canonical mutation',!requests.some(r=>!['GET','HEAD','OPTIONS'].includes(r.method)),{mutations:requests.filter(r=>!['GET','HEAD','OPTIONS'].includes(r.method))});
    check('frontend has no runtime errors',pageErrors.length===0&&consoleErrors.length===0,{pageErrors,consoleErrors});
    return {status:'PASS',checks,requests,responses,pageErrors,consoleErrors,bundle:cfg.expectedBundle,
      remaining:['agent-origin transition','result canonical panel','browser history dirty guard','real backend403 cleanup','native200percent zoom'],
      scope:'UI028/034/041 partial focal only; no provider, AT speech, native execution or release qualification'};
  } catch(error){await shot('failure');return {status:'FAIL',message:error.message,checks,requests,responses,pageErrors,consoleErrors};}
  finally {await page.goto('about:blank');}
}
